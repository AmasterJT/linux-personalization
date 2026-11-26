#include <gtk/gtk.h>
#include <gdk/gdkx.h>
#include <pulse/pulseaudio.h>
#include <pulse/glib-mainloop.h>
#include <math.h>
#include <string.h>

typedef enum { OUTPUT, INPUT, STREAM, NODE_TYPES } Kind;
typedef struct Audio Audio;

typedef struct {
    gint64 last_event, last_step;
    double fraction;
} Scroll;

typedef struct {
    Audio *audio;
    Kind kind;
    guint32 index;
    GtkWidget *scale, *percent, *mute;
    Scroll scroll;
    gboolean syncing;
} Control;

typedef struct {
    Audio *audio;
    Kind kind;
    guint32 index;
    char *name, *description;
    pa_cvolume volume;
    gboolean muted, writable;
    gint64 edited;
    guint settle;
    GtkWidget *row, *selected;
    Control control;
} Node;

typedef struct {
    Kind kind;
    int delta;
    gboolean toggle;
    gint64 deadline;
} Action;

struct Audio {
    GtkApplication *app;
    pa_glib_mainloop *loop;
    pa_context *context;
    GHashTable *nodes[NODE_TYPES];
    char *defaults[2];
    GQueue actions;
    guint reconnect;
    char *error;
    GtkWidget *panel, *lists[NODE_TYPES], *status, *subtitle, *empty;
    Control defaults_ui[2];
    gint64 panel_opened;
    guint panel_timer;
    gboolean mouse_pressed;
    GtkWidget *osd, *meter, *icon, *percent;
    guint osd_timer, tick;
    gint64 osd_deadline, animation_start;
    double shown, start, desired;
    Kind osd_kind;
    gboolean osd_muted;
    Scroll osd_scroll;
};

static const char css[] =
    "#audio-panel, #audio-osd { color: #f1f2f7; border: 1px solid rgba(255,255,255,.10); "
    "font-family: 'Noto Sans'; }"
    "#audio-panel { background: #171922; border-radius: 14px; }"
    "#audio-panel notebook, #audio-panel stack, #audio-panel scrolledwindow, "
    "#audio-panel viewport { background: transparent; border: none; box-shadow: none; }"
    "#audio-panel notebook header { background: transparent; border: none; }"
    "#audio-panel tab { color: #aeb3c2; background: transparent; padding: 6px 12px; "
    "border: none; box-shadow: none; }"
    "#audio-panel tab:checked { color: #fff; border-bottom: 2px solid #f16e44; }"
    "#audio-title { font-weight: bold; font-size: 12pt; }"
    ".audio-detail { color: #a1a6b5; font-size: 9pt; }"
    ".audio-row { background: transparent; border: none; box-shadow: none; padding: 5px; }"
    ".audio-row:hover { background: #252833; }"
    ".audio-active { color: #53ac67; }"
    ".audio-icon { min-width: 28px; color: #f16e44; font: 15pt 'Hack Nerd Font'; }"
    ".audio-icon.muted { color: #898b91; }"
    ".audio-percent { min-width: 44px; font-weight: bold; }"
    "#audio-panel scale trough, #audio-panel scale highlight { min-height: 6px; border-radius: 3px; }"
    "#audio-panel scale trough { background: #343846; }"
    "#audio-panel scale highlight { background: #f16e44; }"
    "#audio-panel scale.muted highlight { background: #757575; }"
    "#audio-panel scale slider { background: #f4f4f4; border: none; border-radius: 8px;"
    "min-width: 16px; min-height: 16px; margin: -5px; }"
    "#audio-osd { background: #25262b; border-radius: 26px; }"
    "#audio-osd .audio-icon { color: #f4f4f4; min-width: 42px; }"
    "#audio-osd .audio-icon.muted { color: #898b91; }";

static int maximum(Kind kind) { return kind == INPUT ? 100 : 150; }

static double volume_level(const Node *node)
{
    return fmin(maximum(node->kind), 100 * pa_sw_volume_to_linear(pa_cvolume_avg(&node->volume)));
}

static gboolean ready(Audio *audio)
{
    return audio->context && pa_context_get_state(audio->context) == PA_CONTEXT_READY;
}

static Node *default_node(Audio *audio, Kind kind)
{
    if (kind == STREAM || !audio->defaults[kind])
        return NULL;
    GHashTableIter iterator;
    gpointer value;
    g_hash_table_iter_init(&iterator, audio->nodes[kind]);
    while (g_hash_table_iter_next(&iterator, NULL, &value)) {
        Node *node = value;
        if (g_strcmp0(node->name, audio->defaults[kind]) == 0)
            return node;
    }
    return NULL;
}

static Node *control_node(Control *control)
{
    return control->index == PA_INVALID_INDEX ? default_node(control->audio, control->kind) :
        g_hash_table_lookup(control->audio->nodes[control->kind], GUINT_TO_POINTER(control->index));
}

static const char *glyph(Kind kind, double level, gboolean mute)
{
    if (kind == INPUT)
        return mute ? "󰍭" : "";
    return mute ? "󰖁" : level < 45 ? "󰕿" : "󰕾";
}

static void text_percent(GtkWidget *label, double value)
{
    char text[16];
    g_snprintf(text, sizeof(text), "%d%%", (int)round(value));
    gtk_label_set_text(GTK_LABEL(label), text);
}

static void style_state(GtkWidget *widget, const char *name, gboolean enabled)
{
    GtkStyleContext *context = gtk_widget_get_style_context(widget);
    if (enabled) gtk_style_context_add_class(context, name);
    else gtk_style_context_remove_class(context, name);
}

static void update_control(Control *control)
{
    if (!control->scale)
        return;
    Node *node = control_node(control);
    double level = node ? volume_level(node) : 0;
    gboolean muted = node && node->muted;
    control->syncing = TRUE;
    gtk_widget_set_sensitive(control->scale, node && node->writable);
    gtk_widget_set_sensitive(control->mute, node != NULL);
    gtk_range_set_value(GTK_RANGE(control->scale), level);
    gtk_button_set_label(GTK_BUTTON(control->mute), glyph(control->kind, level, muted));
    gtk_widget_set_tooltip_text(control->mute, muted ? "Activar sonido" : "Silenciar");
    text_percent(control->percent, level);
    style_state(control->mute, "muted", muted);
    style_state(control->scale, "muted", muted);
    control->syncing = FALSE;
}

static void release_operation(pa_operation *operation)
{
    if (operation)
        pa_operation_unref(operation);
}

static void request_node(Audio *audio, Kind kind, guint32 index);
static void update_panel(Audio *audio);
static void update_osd(Audio *audio, Node *node);

static gboolean settle_node(gpointer data)
{
    Node *node = data;
    node->settle = 0;
    node->edited = 0;
    request_node(node->audio, node->kind, node->index);
    return G_SOURCE_REMOVE;
}

static void mark_edit(Node *node)
{
    node->edited = g_get_monotonic_time();
    if (node->settle)
        g_source_remove(node->settle);
    node->settle = g_timeout_add(200, settle_node, node);
}

static void node_changed(Node *node)
{
    Audio *audio = node->audio;
    if (node->kind == STREAM)
        update_control(&node->control);
    else if (node == default_node(audio, node->kind))
        update_control(&audio->defaults_ui[node->kind]);
    if (audio->osd && gtk_widget_get_visible(audio->osd) && audio->osd_kind == node->kind
        && node == default_node(audio, node->kind))
        update_osd(audio, node);
}

static void set_level(Node *node, double level)
{
    Audio *audio = node->audio;
    if (!ready(audio) || !node->writable)
        return;
    pa_volume_t value = pa_sw_volume_from_linear(CLAMP(level, 0, maximum(node->kind)) / 100.0);
    if (value == pa_cvolume_avg(&node->volume))
        return;
    pa_cvolume_scale(&node->volume, value);
    mark_edit(node);
    pa_context *context = audio->context;
    pa_operation *op;
    switch (node->kind) {
    case OUTPUT: op = pa_context_set_sink_volume_by_index(context, node->index, &node->volume, NULL, NULL); break;
    case INPUT: op = pa_context_set_source_volume_by_index(context, node->index, &node->volume, NULL, NULL); break;
    default: op = pa_context_set_sink_input_volume(context, node->index, &node->volume, NULL, NULL); break;
    }
    release_operation(op);
    node_changed(node);
}

static void set_mute(Node *node, gboolean muted)
{
    Audio *audio = node->audio;
    if (!ready(audio) || node->muted == muted)
        return;
    node->muted = muted;
    mark_edit(node);
    pa_context *context = audio->context;
    pa_operation *op;
    switch (node->kind) {
    case OUTPUT: op = pa_context_set_sink_mute_by_index(context, node->index, muted, NULL, NULL); break;
    case INPUT: op = pa_context_set_source_mute_by_index(context, node->index, muted, NULL, NULL); break;
    default: op = pa_context_set_sink_input_mute(context, node->index, muted, NULL, NULL); break;
    }
    release_operation(op);
    node_changed(node);
}

/* An ordinary notch is 2 percentage points. Smooth devices contribute
   fractional notches and a high-resolution burst cannot enqueue a tail. */
static int scroll_change(Scroll *scroll, GdkEventScroll *event)
{
    gint64 now = g_get_monotonic_time();
    double x = 0, y = 0;
    if (event->direction == GDK_SCROLL_SMOOTH) {
        if (!gdk_event_get_scroll_deltas((GdkEvent *)event, &x, &y) || fabs(x) > fabs(y))
            return 0;
        y = -y;
    } else if (event->direction == GDK_SCROLL_UP) y = 1;
    else if (event->direction == GDK_SCROLL_DOWN) y = -1;
    else return 0;
    if (now - scroll->last_event > 250000 || y * scroll->fraction < 0)
        scroll->fraction = 0;
    scroll->last_event = now;
    scroll->fraction += y;
    if (fabs(scroll->fraction) < 1)
        return 0;
    int direction = scroll->fraction > 0 ? 1 : -1;
    scroll->fraction = 0;
    if (now - scroll->last_step < 65000)
        return 0;
    scroll->last_step = now;
    return 2 * direction;
}

static gboolean scale_scroll(GtkWidget *widget, GdkEventScroll *event, gpointer data)
{
    Control *control = data;
    int delta = scroll_change(&control->scroll, event);
    if (delta)
        gtk_range_set_value(GTK_RANGE(widget), round(gtk_range_get_value(GTK_RANGE(widget))) + delta);
    return TRUE;
}

static void scale_changed(GtkRange *range, gpointer data)
{
    Control *control = data;
    Node *node = control_node(control);
    if (!control->syncing && node)
        set_level(node, gtk_range_get_value(range));
}

static void mute_clicked(GtkButton *button, gpointer data)
{
    (void)button;
    Node *node = control_node(data);
    if (node)
        set_mute(node, !node->muted);
}

static GtkWidget *label_left(const char *value, const char *class)
{
    GtkWidget *label = gtk_label_new(value);
    gtk_label_set_xalign(GTK_LABEL(label), 0);
    gtk_label_set_ellipsize(GTK_LABEL(label), PANGO_ELLIPSIZE_END);
    if (class) style_state(label, class, TRUE);
    return label;
}

static GtkWidget *control_row(Control *control, Audio *audio, Kind kind, guint32 index)
{
    *control = (Control){ .audio = audio, .kind = kind, .index = index };
    GtkWidget *row = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 9);
    control->mute = gtk_button_new_with_label(glyph(kind, 50, FALSE));
    style_state(control->mute, "audio-row", TRUE);
    style_state(control->mute, "audio-icon", TRUE);
    control->scale = gtk_scale_new_with_range(GTK_ORIENTATION_HORIZONTAL, 0, maximum(kind), 1);
    gtk_scale_set_draw_value(GTK_SCALE(control->scale), FALSE);
    gtk_widget_add_events(control->scale, GDK_SCROLL_MASK | GDK_SMOOTH_SCROLL_MASK);
    control->percent = gtk_label_new("0%");
    gtk_label_set_xalign(GTK_LABEL(control->percent), 1);
    style_state(control->percent, "audio-percent", TRUE);
    gtk_box_pack_start(GTK_BOX(row), control->mute, FALSE, FALSE, 0);
    gtk_box_pack_start(GTK_BOX(row), control->scale, TRUE, TRUE, 0);
    gtk_box_pack_start(GTK_BOX(row), control->percent, FALSE, FALSE, 0);
    g_signal_connect(control->mute, "clicked", G_CALLBACK(mute_clicked), control);
    g_signal_connect(control->scale, "value-changed", G_CALLBACK(scale_changed), control);
    g_signal_connect(control->scale, "scroll-event", G_CALLBACK(scale_scroll), control);
    update_control(control);
    return row;
}

static GtkWidget *scrolled(GtkWidget *content)
{
    GtkWidget *scroll = gtk_scrolled_window_new(NULL, NULL);
    gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(scroll), GTK_POLICY_NEVER, GTK_POLICY_AUTOMATIC);
    gtk_container_add(GTK_CONTAINER(scroll), content);
    return scroll;
}

static void choose_device(GtkButton *button, gpointer data)
{
    (void)button;
    Node *node = data;
    if (!ready(node->audio))
        return;
    release_operation(node->kind == OUTPUT
        ? pa_context_set_default_sink(node->audio->context, node->name, NULL, NULL)
        : pa_context_set_default_source(node->audio->context, node->name, NULL, NULL));
}

static void add_row(Node *node, const char *icon_name)
{
    Audio *audio = node->audio;
    if (!audio->panel || node->row)
        return;
    GtkWidget *row = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 8);
    if (node->kind == STREAM) {
        GtkIconTheme *theme = gtk_icon_theme_get_default();
        const char *name = icon_name && gtk_icon_theme_has_icon(theme, icon_name)
            ? icon_name : "application-x-executable";
        GtkWidget *image = gtk_image_new_from_icon_name(name, GTK_ICON_SIZE_BUTTON);
        gtk_image_set_pixel_size(GTK_IMAGE(image), 24);
        GtkWidget *label = label_left(node->description, NULL);
        gtk_widget_set_size_request(label, 105, -1);
        gtk_widget_set_tooltip_text(label, node->description);
        gtk_box_pack_start(GTK_BOX(row), image, FALSE, FALSE, 0);
        gtk_box_pack_start(GTK_BOX(row), label, FALSE, FALSE, 0);
        gtk_box_pack_start(GTK_BOX(row), control_row(&node->control, audio, STREAM, node->index), TRUE, TRUE, 0);
        node->row = row;
    } else {
        GtkWidget *button = gtk_button_new();
        gtk_container_add(GTK_CONTAINER(button), row);
        style_state(button, "audio-row", TRUE);
        GtkWidget *icon = gtk_label_new(glyph(node->kind, 50, FALSE));
        style_state(icon, "audio-icon", TRUE);
        node->selected = gtk_label_new("");
        style_state(node->selected, "audio-active", TRUE);
        gtk_box_pack_start(GTK_BOX(row), icon, FALSE, FALSE, 0);
        gtk_box_pack_start(GTK_BOX(row), label_left(node->description, NULL), TRUE, TRUE, 0);
        gtk_box_pack_start(GTK_BOX(row), node->selected, FALSE, FALSE, 0);
        g_signal_connect(button, "clicked", G_CALLBACK(choose_device), node);
        node->row = button;
    }
    gtk_box_pack_start(GTK_BOX(audio->lists[node->kind]), node->row, FALSE, FALSE, 0);
    gtk_widget_show_all(node->row);
}

static void node_free(gpointer data)
{
    Node *node = data;
    if (node->settle) g_source_remove(node->settle);
    if (node->row) gtk_widget_destroy(node->row);
    g_free(node->name);
    g_free(node->description);
    g_free(node);
}

static void update_panel(Audio *audio)
{
    if (!audio->panel)
        return;
    Node *output = default_node(audio, OUTPUT), *input = default_node(audio, INPUT);
    g_autofree char *summary = g_strdup_printf("%s · %s",
        output ? output->description : "Sin salida", input ? input->description : "Sin micrófono");
    gtk_label_set_text(GTK_LABEL(audio->subtitle), summary);
    guint streams = g_hash_table_size(audio->nodes[STREAM]);
    g_autofree char *counts = g_strdup_printf("%u salidas · %u entradas · %u aplicaciones",
        g_hash_table_size(audio->nodes[OUTPUT]), g_hash_table_size(audio->nodes[INPUT]), streams);
    gtk_label_set_text(GTK_LABEL(audio->status), audio->error ? audio->error : counts);
    gtk_widget_set_visible(audio->empty, streams == 0);
    for (Kind kind = OUTPUT; kind <= INPUT; kind++) {
        Node *active = kind == OUTPUT ? output : input;
        GHashTableIter iter;
        gpointer value;
        g_hash_table_iter_init(&iter, audio->nodes[kind]);
        while (g_hash_table_iter_next(&iter, NULL, &value)) {
            Node *node = value;
            gtk_label_set_text(GTK_LABEL(node->selected), node == active ? "✓" : "");
        }
        if (active)
            gtk_box_reorder_child(GTK_BOX(audio->lists[kind]), active->row, 0);
        update_control(&audio->defaults_ui[kind]);
    }
}

static void settings(GtkButton *button, gpointer data)
{
    (void)button;
    Audio *audio = data;
    g_autofree char *program = g_find_program_in_path("pavucontrol");
    g_spawn_command_line_async(program ? "pavucontrol" : "gnome-control-center sound", NULL);
    gtk_widget_hide(audio->panel);
}

static gboolean panel_key(GtkWidget *window, GdkEventKey *event, gpointer data)
{
    (void)data;
    if (event->keyval != GDK_KEY_Escape)
        return FALSE;
    gtk_widget_hide(window);
    return TRUE;
}

static gboolean hide_window(GtkWidget *window, GdkEvent *event, gpointer data)
{
    (void)event;
    (void)data;
    gtk_widget_hide(window);
    return TRUE;
}

static gboolean pointer_over(GtkWidget *window, gboolean *pressed)
{
    GdkDisplay *display = gtk_widget_get_display(window);
    GdkDevice *pointer = gdk_seat_get_pointer(gdk_display_get_default_seat(display));
    gint px, py, x, y, width, height;
    GdkModifierType masks;
    GdkWindow *root = gdk_screen_get_root_window(gtk_widget_get_screen(window));
    gdk_device_get_position(pointer, NULL, &px, &py);
    gdk_device_get_state(pointer, root, NULL, &masks);
    if (pressed) *pressed = (masks & (GDK_BUTTON1_MASK | GDK_BUTTON2_MASK | GDK_BUTTON3_MASK)) != 0;
    gtk_window_get_position(GTK_WINDOW(window), &x, &y);
    gtk_window_get_size(GTK_WINDOW(window), &width, &height);
    return px >= x && px < x + width && py >= y && py < y + height;
}

static gboolean outside_click(gpointer data)
{
    Audio *audio = data;
    if (!gtk_widget_get_visible(audio->panel)) {
        audio->panel_timer = 0;
        return G_SOURCE_REMOVE;
    }
    gboolean pressed;
    gboolean inside = pointer_over(audio->panel, &pressed);
    if (pressed && !audio->mouse_pressed && !inside && g_get_monotonic_time() - audio->panel_opened > 230000)
        gtk_widget_hide(audio->panel);
    audio->mouse_pressed = pressed;
    return G_SOURCE_CONTINUE;
}

static gboolean panel_focus_out(GtkWidget *window, GdkEventFocus *event, gpointer data)
{
    (void)event;
    Audio *audio = data;
    if (g_get_monotonic_time() - audio->panel_opened > 230000 && !pointer_over(window, NULL))
        gtk_widget_hide(window);
    return FALSE;
}

static GtkWidget *window_new(Audio *audio, const char *title, const char *name, gboolean osd)
{
    GtkWidget *window = gtk_application_window_new(audio->app);
    gtk_widget_set_name(window, name);
    gtk_window_set_title(GTK_WINDOW(window), title);
    gtk_window_set_decorated(GTK_WINDOW(window), FALSE);
    gtk_window_set_resizable(GTK_WINDOW(window), FALSE);
    gtk_window_set_keep_above(GTK_WINDOW(window), TRUE);
    gtk_window_set_skip_taskbar_hint(GTK_WINDOW(window), TRUE);
    gtk_window_set_skip_pager_hint(GTK_WINDOW(window), TRUE);
    gtk_window_set_accept_focus(GTK_WINDOW(window), !osd);
    gtk_window_set_focus_on_map(GTK_WINDOW(window), !osd);
    gtk_window_set_type_hint(GTK_WINDOW(window), osd ? GDK_WINDOW_TYPE_HINT_NOTIFICATION : GDK_WINDOW_TYPE_HINT_DIALOG);
    GdkVisual *visual = gdk_screen_get_rgba_visual(gtk_widget_get_screen(window));
    if (visual) gtk_widget_set_visual(window, visual);
    g_signal_connect(window, "delete-event", G_CALLBACK(hide_window), NULL);
    return window;
}

static void place(GtkWidget *window, gboolean osd)
{
    GdkDisplay *display = gtk_widget_get_display(window);
    GdkMonitor *monitor = gdk_display_get_primary_monitor(display);
    if (!monitor) monitor = gdk_display_get_monitor(display, 0);
    GdkRectangle geometry;
    gdk_monitor_get_geometry(monitor, &geometry);
    GtkRequisition natural;
    gtk_widget_get_preferred_size(window, NULL, &natural);
    int width = MAX(natural.width, osd ? 390 : 540);
    int height = MAX(natural.height, osd ? 58 : 400);
    int x = osd ? geometry.x + (geometry.width - width) / 2 :
        geometry.x + (int)(geometry.width * .9684) - width;
    int y = osd ? geometry.y + geometry.height - height - 95 : geometry.y + 48;
    gtk_window_move(GTK_WINDOW(window), MAX(geometry.x, x), y);
    gtk_widget_realize(window);
    gdk_window_move(gtk_widget_get_window(window), MAX(geometry.x, x), y);
}

static void build_panel(Audio *audio)
{
    GtkWidget *window = audio->panel = window_new(audio, "Audio BSPWM", "audio-panel", FALSE);
    G_GNUC_BEGIN_IGNORE_DEPRECATIONS
    gtk_window_set_wmclass(GTK_WINDOW(window), "bspwm-audio", "BspwmPolybarPopup");
    G_GNUC_END_IGNORE_DEPRECATIONS
    gtk_window_set_default_size(GTK_WINDOW(window), 540, 400);
    GtkWidget *card = gtk_box_new(GTK_ORIENTATION_VERTICAL, 9);
    gtk_container_set_border_width(GTK_CONTAINER(card), 16);
    gtk_container_add(GTK_CONTAINER(window), card);
    GtkWidget *title = label_left("Audio", NULL);
    gtk_widget_set_name(title, "audio-title");
    gtk_box_pack_start(GTK_BOX(card), title, FALSE, FALSE, 0);
    audio->subtitle = label_left("", "audio-detail");
    gtk_label_set_max_width_chars(GTK_LABEL(audio->subtitle), 64);
    gtk_box_pack_start(GTK_BOX(card), audio->subtitle, FALSE, FALSE, 0);
    GtkWidget *notebook = gtk_notebook_new();
    gtk_box_pack_start(GTK_BOX(card), notebook, TRUE, TRUE, 0);
    for (Kind kind = OUTPUT; kind < NODE_TYPES; kind++) {
        GtkWidget *box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 8);
        gtk_container_set_border_width(GTK_CONTAINER(box), 8);
        audio->lists[kind] = gtk_box_new(GTK_ORIENTATION_VERTICAL, 3);
        if (kind != STREAM) {
            gtk_box_pack_start(GTK_BOX(box), label_left(kind == OUTPUT ? "Volumen general" : "Nivel del micrófono",
                              "audio-detail"), FALSE, FALSE, 0);
            gtk_box_pack_start(GTK_BOX(box), control_row(&audio->defaults_ui[kind], audio, kind,
                               PA_INVALID_INDEX), FALSE, FALSE, 0);
            gtk_box_pack_start(GTK_BOX(box), gtk_separator_new(GTK_ORIENTATION_HORIZONTAL), FALSE, FALSE, 0);
            gtk_box_pack_start(GTK_BOX(box), label_left(kind == OUTPUT ? "Salidas disponibles" : "Entradas disponibles",
                              "audio-detail"), FALSE, FALSE, 0);
        } else {
            audio->empty = label_left("No hay aplicaciones reproduciendo audio", "audio-detail");
            gtk_widget_set_no_show_all(audio->empty, TRUE);
            gtk_box_pack_start(GTK_BOX(box), audio->empty, FALSE, FALSE, 0);
        }
        gtk_box_pack_start(GTK_BOX(box), scrolled(audio->lists[kind]), TRUE, TRUE, 0);
        const char *tab = kind == OUTPUT ? "Salida" : kind == INPUT ? "Micrófono" : "Aplicaciones";
        gtk_notebook_append_page(GTK_NOTEBOOK(notebook), box, gtk_label_new(tab));
        GHashTableIter iter;
        gpointer value;
        g_hash_table_iter_init(&iter, audio->nodes[kind]);
        while (g_hash_table_iter_next(&iter, NULL, &value)) {
            Node *node = value;
            add_row(node, kind == STREAM ? node->name : NULL);
        }
    }
    GtkWidget *footer = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 10);
    audio->status = label_left("", "audio-detail");
    GtkWidget *button = gtk_button_new_with_label("Configuración de sonido");
    g_signal_connect(button, "clicked", G_CALLBACK(settings), audio);
    gtk_box_pack_start(GTK_BOX(footer), audio->status, TRUE, TRUE, 0);
    gtk_box_pack_end(GTK_BOX(footer), button, FALSE, FALSE, 0);
    gtk_box_pack_end(GTK_BOX(card), footer, FALSE, FALSE, 0);
    g_signal_connect(window, "key-press-event", G_CALLBACK(panel_key), audio);
    g_signal_connect(window, "focus-out-event", G_CALLBACK(panel_focus_out), audio);
    gtk_widget_show_all(card);
    update_panel(audio);
}

static void toggle_panel(Audio *audio)
{
    if (!audio->panel) build_panel(audio);
    if (gtk_widget_get_visible(audio->panel)) {
        gtk_widget_hide(audio->panel);
        return;
    }
    place(audio->panel, FALSE);
    audio->panel_opened = g_get_monotonic_time();
    pointer_over(audio->panel, &audio->mouse_pressed);
    gtk_window_present(GTK_WINDOW(audio->panel));
    if (!audio->panel_timer) audio->panel_timer = g_timeout_add(35, outside_click, audio);
}

static gboolean draw_meter(GtkWidget *widget, cairo_t *cr, gpointer data)
{
    Audio *audio = data;
    double width = gtk_widget_get_allocated_width(widget);
    double y = gtk_widget_get_allocated_height(widget) / 2.0;
    double boundary = width * 2 / 3;
    double fill = width * audio->shown / maximum(audio->osd_kind);
    cairo_save(cr);
    cairo_new_sub_path(cr);
    cairo_arc(cr, width - 3, y, 3, -G_PI / 2, G_PI / 2);
    cairo_arc(cr, 3, y, 3, G_PI / 2, 3 * G_PI / 2);
    cairo_close_path(cr);
    cairo_clip(cr);
    cairo_set_source_rgb(cr, .25, .26, .29);
    cairo_paint(cr);
    double first = audio->osd_kind == OUTPUT ? fmin(fill, boundary) : fill;
    cairo_rectangle(cr, 0, y - 3, first, 6);
    cairo_set_source_rgb(cr, audio->osd_muted ? .54 : .96, audio->osd_muted ? .55 : .96,
                         audio->osd_muted ? .57 : .96);
    cairo_fill(cr);
    if (audio->osd_kind == OUTPUT && fill > boundary) {
        cairo_rectangle(cr, boundary, y - 3, fill - boundary, 6);
        cairo_set_source_rgb(cr, audio->osd_muted ? .54 : .91, audio->osd_muted ? .55 : .24,
                             audio->osd_muted ? .57 : .31);
        cairo_fill(cr);
    }
    cairo_restore(cr);
    if (audio->osd_kind == OUTPUT) {
        cairo_rectangle(cr, boundary - 1, y - 4, 2, 8);
        cairo_set_source_rgb(cr, .62, .64, .67);
        cairo_fill(cr);
    }
    return FALSE;
}

static gboolean animate(GtkWidget *widget, GdkFrameClock *clock, gpointer data)
{
    Audio *audio = data;
    double t = CLAMP((gdk_frame_clock_get_frame_time(clock) - audio->animation_start) / 120000.0, 0, 1);
    audio->shown = audio->start + (audio->desired - audio->start) * (1 - (1 - t) * (1 - t));
    gtk_widget_queue_draw(widget);
    if (t < 1) return G_SOURCE_CONTINUE;
    audio->tick = 0;
    return G_SOURCE_REMOVE;
}

static void update_osd(Audio *audio, Node *node)
{
    double level = volume_level(node);
    audio->osd_muted = node->muted;
    gtk_button_set_label(GTK_BUTTON(audio->icon), glyph(node->kind, level, node->muted));
    gtk_widget_set_tooltip_text(audio->icon, node->muted ? "Activar sonido" : "Silenciar");
    style_state(audio->icon, "muted", node->muted);
    text_percent(audio->percent, level);
    if (!gtk_widget_get_visible(audio->osd)) {
        if (audio->tick) gtk_widget_remove_tick_callback(audio->meter, audio->tick);
        audio->tick = 0;
        audio->shown = audio->desired = level;
    } else if (fabs(level - audio->desired) > .001) {
        audio->start = audio->shown;
        audio->desired = level;
        audio->animation_start = g_get_monotonic_time();
        if (!audio->tick) audio->tick = gtk_widget_add_tick_callback(audio->meter, animate, audio, NULL);
    }
    gtk_widget_queue_draw(audio->meter);
}

static gboolean osd_timeout(gpointer data)
{
    Audio *audio = data;
    if (pointer_over(audio->osd, NULL))
        audio->osd_deadline = g_get_monotonic_time() + 1800000;
    if (g_get_monotonic_time() < audio->osd_deadline)
        return G_SOURCE_CONTINUE;
    gtk_widget_hide(audio->osd);
    audio->osd_timer = 0;
    return G_SOURCE_REMOVE;
}

static void osd_mute(GtkButton *button, gpointer data)
{
    (void)button;
    Audio *audio = data;
    Node *node = default_node(audio, audio->osd_kind);
    if (node) set_mute(node, !node->muted);
    audio->osd_deadline = g_get_monotonic_time() + 1800000;
}

static gboolean osd_scroll(GtkWidget *widget, GdkEventScroll *event, gpointer data)
{
    (void)widget;
    Audio *audio = data;
    Node *node = default_node(audio, audio->osd_kind);
    if (node && audio->osd_kind == OUTPUT) {
        int delta = scroll_change(&audio->osd_scroll, event);
        if (delta) set_level(node, round(volume_level(node)) + delta);
        audio->osd_deadline = g_get_monotonic_time() + 1800000;
    }
    return TRUE;
}

static void show_osd(Audio *audio, Node *node)
{
    if (!audio->osd) {
        audio->osd = window_new(audio, "Controles BSPWM", "audio-osd", TRUE);
        gtk_window_set_default_size(GTK_WINDOW(audio->osd), 390, 58);
        GtkWidget *row = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 10);
        gtk_container_set_border_width(GTK_CONTAINER(row), 10);
        gtk_container_add(GTK_CONTAINER(audio->osd), row);
        audio->icon = gtk_button_new();
        style_state(audio->icon, "audio-row", TRUE);
        style_state(audio->icon, "audio-icon", TRUE);
        audio->meter = gtk_drawing_area_new();
        audio->percent = gtk_label_new("");
        style_state(audio->percent, "audio-percent", TRUE);
        gtk_label_set_xalign(GTK_LABEL(audio->percent), 1);
        /* Match the inset from the left edge to the centered speaker glyph. */
        gtk_widget_set_margin_end(audio->percent, 18);
        gtk_box_pack_start(GTK_BOX(row), audio->icon, FALSE, FALSE, 0);
        gtk_box_pack_start(GTK_BOX(row), audio->meter, TRUE, TRUE, 0);
        gtk_box_pack_end(GTK_BOX(row), audio->percent, FALSE, FALSE, 0);
        g_signal_connect(audio->icon, "clicked", G_CALLBACK(osd_mute), audio);
        g_signal_connect(audio->meter, "draw", G_CALLBACK(draw_meter), audio);
        gtk_widget_add_events(audio->osd, GDK_SCROLL_MASK | GDK_SMOOTH_SCROLL_MASK);
        g_signal_connect(audio->osd, "scroll-event", G_CALLBACK(osd_scroll), audio);
        gtk_widget_show_all(row);
    }
    audio->osd_kind = node->kind;
    update_osd(audio, node);
    audio->osd_deadline = g_get_monotonic_time() + 1800000;
    if (!gtk_widget_get_visible(audio->osd)) {
        audio->osd_scroll = (Scroll){0};
        place(audio->osd, TRUE);
        gtk_widget_show(audio->osd);
    }
    if (!audio->osd_timer) audio->osd_timer = g_timeout_add(80, osd_timeout, audio);
}

static void process_actions(Audio *audio)
{
    if (!ready(audio))
        return;
    for (GList *link = audio->actions.head, *next; link; link = next) {
        next = link->next;
        Action *action = link->data;
        if (g_get_monotonic_time() >= action->deadline) {
            g_queue_delete_link(&audio->actions, link);
            g_free(action);
            continue;
        }
        Node *node = default_node(audio, action->kind);
        if (!node) continue;
        if (action->toggle) set_mute(node, !node->muted);
        else {
            set_level(node, round(volume_level(node)) + action->delta);
            set_mute(node, FALSE);
        }
        show_osd(audio, node);
        g_queue_delete_link(&audio->actions, link);
        g_free(action);
    }
}

static void snapshot(Audio *audio, Kind kind, guint32 index, const char *name, const char *description,
                     const pa_cvolume *volume, gboolean muted, gboolean writable)
{
    Node *node = g_hash_table_lookup(audio->nodes[kind], GUINT_TO_POINTER(index));
    gboolean fresh = !node;
    if (fresh) {
        node = g_new0(Node, 1);
        node->audio = audio;
        node->kind = kind;
        node->index = index;
        node->name = g_strdup(name);
        node->description = g_strdup(description && *description ? description : "Audio");
        g_hash_table_insert(audio->nodes[kind], GUINT_TO_POINTER(index), node);
    }
    if (fresh || !node->edited || g_get_monotonic_time() - node->edited >= 200000) {
        node->volume = *volume;
        node->muted = muted;
    }
    node->writable = writable && pa_cvolume_valid(volume);
    if (fresh) {
        add_row(node, kind == STREAM ? name : NULL);
        update_panel(audio);
    }
    node_changed(node);
    process_actions(audio);
}

static void sink_info(pa_context *context, const pa_sink_info *i, int eol, void *data)
{
    (void)context;
    if (!eol && i) snapshot(data, OUTPUT, i->index, i->name, i->description, &i->volume, i->mute, TRUE);
}

static void source_info(pa_context *context, const pa_source_info *i, int eol, void *data)
{
    (void)context;
    if (!eol && i) snapshot(data, INPUT, i->index, i->name, i->description, &i->volume, i->mute, TRUE);
}

static void stream_info(pa_context *context, const pa_sink_input_info *i, int eol, void *data)
{
    (void)context;
    if (eol || !i) return;
    const char *name = pa_proplist_gets(i->proplist, PA_PROP_APPLICATION_NAME);
    const char *icon = pa_proplist_gets(i->proplist, PA_PROP_APPLICATION_ICON_NAME);
    if (!icon) icon = pa_proplist_gets(i->proplist, PA_PROP_APPLICATION_PROCESS_BINARY);
    snapshot(data, STREAM, i->index, icon, name ? name : i->name, &i->volume, i->mute,
             i->has_volume && i->volume_writable);
}

static void server_info(pa_context *context, const pa_server_info *i, void *data)
{
    (void)context;
    Audio *audio = data;
    if (!i) return;
    g_free(audio->defaults[OUTPUT]);
    g_free(audio->defaults[INPUT]);
    audio->defaults[OUTPUT] = g_strdup(i->default_sink_name);
    audio->defaults[INPUT] = g_strdup(i->default_source_name);
    update_panel(audio);
    Node *current = default_node(audio, audio->osd_kind);
    if (current && audio->osd && gtk_widget_get_visible(audio->osd)) update_osd(audio, current);
    process_actions(audio);
}

static void request_node(Audio *audio, Kind kind, guint32 index)
{
    if (!ready(audio)) return;
    pa_context *context = audio->context;
    switch (kind) {
    case OUTPUT: release_operation(pa_context_get_sink_info_by_index(context, index, sink_info, audio)); break;
    case INPUT: release_operation(pa_context_get_source_info_by_index(context, index, source_info, audio)); break;
    default: release_operation(pa_context_get_sink_input_info(context, index, stream_info, audio)); break;
    }
}

static void subscription(pa_context *context, pa_subscription_event_type_t type, guint32 index, void *data)
{
    Audio *audio = data;
    Kind kind;
    switch (type & PA_SUBSCRIPTION_EVENT_FACILITY_MASK) {
    case PA_SUBSCRIPTION_EVENT_SINK: kind = OUTPUT; break;
    case PA_SUBSCRIPTION_EVENT_SOURCE: kind = INPUT; break;
    case PA_SUBSCRIPTION_EVENT_SINK_INPUT: kind = STREAM; break;
    case PA_SUBSCRIPTION_EVENT_SERVER:
        release_operation(pa_context_get_server_info(context, server_info, audio));
        return;
    default: return;
    }
    if ((type & PA_SUBSCRIPTION_EVENT_TYPE_MASK) == PA_SUBSCRIPTION_EVENT_REMOVE) {
        g_hash_table_remove(audio->nodes[kind], GUINT_TO_POINTER(index));
        update_panel(audio);
    } else request_node(audio, kind, index);
}

static gboolean connect_audio(gpointer data);

static void state_changed(pa_context *context, void *data)
{
    Audio *audio = data;
    switch (pa_context_get_state(context)) {
    case PA_CONTEXT_READY:
        g_clear_pointer(&audio->error, g_free);
        pa_context_set_subscribe_callback(context, subscription, audio);
        release_operation(pa_context_subscribe(context, PA_SUBSCRIPTION_MASK_SINK |
            PA_SUBSCRIPTION_MASK_SOURCE | PA_SUBSCRIPTION_MASK_SINK_INPUT | PA_SUBSCRIPTION_MASK_SERVER, NULL, NULL));
        release_operation(pa_context_get_server_info(context, server_info, audio));
        release_operation(pa_context_get_sink_info_list(context, sink_info, audio));
        release_operation(pa_context_get_source_info_list(context, source_info, audio));
        release_operation(pa_context_get_sink_input_info_list(context, stream_info, audio));
        break;
    case PA_CONTEXT_FAILED: case PA_CONTEXT_TERMINATED:
        g_free(audio->error);
        audio->error = g_strdup("Conexión de audio interrumpida. Reconectando…");
        for (int kind = 0; kind < NODE_TYPES; kind++) g_hash_table_remove_all(audio->nodes[kind]);
        g_queue_clear_full(&audio->actions, g_free);
        update_panel(audio);
        if (!audio->reconnect) audio->reconnect = g_timeout_add_seconds(2, connect_audio, audio);
        break;
    default: break;
    }
}

static gboolean connect_audio(gpointer data)
{
    Audio *audio = data;
    audio->reconnect = 0;
    if (audio->context) {
        pa_context_set_state_callback(audio->context, NULL, NULL);
        pa_context_unref(audio->context);
    }
    audio->context = pa_context_new(pa_glib_mainloop_get_api(audio->loop), "Controles BSPWM");
    pa_context_set_state_callback(audio->context, state_changed, audio);
    if (pa_context_connect(audio->context, NULL, PA_CONTEXT_NOAUTOSPAWN, NULL) < 0)
        state_changed(audio->context, audio);
    return G_SOURCE_REMOVE;
}

static void startup(GApplication *app, gpointer data)
{
    Audio *audio = data;
    g_application_hold(app);
    GtkCssProvider *provider = gtk_css_provider_new();
    gtk_css_provider_load_from_data(provider, css, -1, NULL);
    gtk_style_context_add_provider_for_screen(gdk_screen_get_default(), GTK_STYLE_PROVIDER(provider),
                                               GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);
    g_object_unref(provider);
    for (int kind = 0; kind < NODE_TYPES; kind++)
        audio->nodes[kind] = g_hash_table_new_full(g_direct_hash, g_direct_equal, NULL, node_free);
    audio->loop = pa_glib_mainloop_new(NULL);
    connect_audio(audio);
}

static int command_line(GApplication *app, GApplicationCommandLine *command, gpointer data)
{
    Audio *audio = data;
    int argc;
    g_auto(GStrv) argv = g_application_command_line_get_arguments(command, &argc);
    if (argc == 2 && g_str_equal(argv[1], "panel")) {
        toggle_panel(audio);
        return 0;
    }
    if (argc == 2 && g_str_equal(argv[1], "quit")) {
        g_application_quit(app);
        return 0;
    }
    if (argc >= 3 && (g_str_equal(argv[1], "volume") || g_str_equal(argv[1], "microphone"))) {
        Kind kind = g_str_equal(argv[1], "volume") ? OUTPUT : INPUT;
        gboolean toggle = argc == 3 && g_str_equal(argv[2], "mute");
        char *end = NULL;
        gint64 delta = argc == 4 && kind == OUTPUT && g_str_equal(argv[2], "change")
            ? g_ascii_strtoll(argv[3], &end, 10) : 0;
        if (toggle || (end && end != argv[3] && !*end && delta >= -150 && delta <= 150)) {
            Action *action = g_new(Action, 1);
            *action = (Action){ .kind = kind, .delta = (int)delta, .toggle = toggle,
                                .deadline = g_get_monotonic_time() + G_TIME_SPAN_SECOND };
            if (audio->actions.length == 32) g_free(g_queue_pop_head(&audio->actions));
            g_queue_push_tail(&audio->actions, action);
            process_actions(audio);
            return 0;
        }
    }
    g_application_command_line_printerr(command, "Uso: audio-control panel | volume change N | volume mute | microphone mute\n");
    return 2;
}

int main(int argc, char **argv)
{
    gdk_set_allowed_backends("x11");
    g_autoptr(GtkApplication) app = gtk_application_new("org.linuxpersonalization.BspwmAudio",
                                                        G_APPLICATION_HANDLES_COMMAND_LINE);
    Audio audio = { .app = app };
    g_signal_connect(app, "startup", G_CALLBACK(startup), &audio);
    g_signal_connect(app, "command-line", G_CALLBACK(command_line), &audio);
    int result = g_application_run(G_APPLICATION(app), argc, argv);
    if (audio.context) {
        pa_context_set_state_callback(audio.context, NULL, NULL);
        pa_context_disconnect(audio.context);
        pa_context_unref(audio.context);
    }
    if (audio.loop) pa_glib_mainloop_free(audio.loop);
    for (int kind = 0; kind < NODE_TYPES; kind++)
        if (audio.nodes[kind]) g_hash_table_unref(audio.nodes[kind]);
    g_queue_clear_full(&audio.actions, g_free);
    g_free(audio.defaults[OUTPUT]);
    g_free(audio.defaults[INPUT]);
    g_free(audio.error);
    return result;
}
