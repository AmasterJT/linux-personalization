#define _GNU_SOURCE
#define WNCK_I_KNOW_THIS_IS_UNSTABLE

#include <cairo-xlib-xrender.h>
#include <gdk/gdkx.h>
#include <glib-unix.h>
#include <gtk/gtk.h>
#include <libwnck/libwnck.h>
#include <X11/extensions/Xcomposite.h>
#include <X11/extensions/Xrender.h>

#include <errno.h>
#include <fcntl.h>
#include <stddef.h>
#include <string.h>
#include <sys/file.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

enum { MAX_COLUMNS = 4, VISIBLE_ROWS = 2, GAP = 10, CARD_HEIGHT = 160 };

static const char css[] =
    "#switcher-window { background-color: rgba(20,22,30,0.97);"
    " border: 1px solid rgba(255,255,255,0.10); border-radius: 12px; }"
    "#switcher-card { background: transparent; border: 2px solid transparent;"
    " border-radius: 13px; box-shadow: none; padding: 8px; }"
    "#switcher-card:hover { background: #282c39; }"
    "#switcher-card.selected { background: #303645; border-color: #f16e44; }"
    "#preview-frame { background: #0d1017; border-radius: 8px; padding: 2px; }"
    "#switcher-window scrollbar slider { background: #444a5b;"
    " border-radius: 4px; min-width: 6px; min-height: 24px; }";

typedef struct {
    WnckWindow *client; /* Owned by the WnckHandle. */
    GtkWidget *button;
    GtkWidget *image;
    gboolean captured;
} Entry;

typedef struct {
    GtkWidget *window;
    GtkAdjustment *scroll;
    GArray *entries;
    GdkDisplay *display;
    Display *xdisplay;
    int columns, preview_width, selected;
    gboolean composite, closing, first_frame;
} Switcher;

static void collect_windows(Switcher *switcher, WnckScreen *screen)
{
    wnck_screen_force_update(screen);
    WnckWindow *active = wnck_screen_get_active_window(screen);
    WnckWorkspace *workspace = wnck_screen_get_active_workspace(screen);
    for (GList *item = g_list_last(wnck_screen_get_windows_stacked(screen)); item; item = item->prev) {
        WnckWindow *window = item->data;
        WnckWindowType type = wnck_window_get_window_type(window);
        if (wnck_window_is_skip_tasklist(window) ||
            (type != WNCK_WINDOW_NORMAL && type != WNCK_WINDOW_DIALOG && type != WNCK_WINDOW_UTILITY) ||
            (workspace && !wnck_window_is_on_workspace(window, workspace)))
            continue;

        Entry entry = { .client = g_object_ref(window) };
        if (window == active)
            g_array_prepend_val(switcher->entries, entry);
        else
            g_array_append_val(switcher->entries, entry);
    }
}

static gboolean has_preview_pixels(GdkPixbuf *pixbuf)
{
    int width = gdk_pixbuf_get_width(pixbuf), height = gdk_pixbuf_get_height(pixbuf);
    int stride = gdk_pixbuf_get_rowstride(pixbuf), channels = gdk_pixbuf_get_n_channels(pixbuf);
    const guchar *pixels = gdk_pixbuf_read_pixels(pixbuf);
    int visible = 0;
    for (int y = 0; y < height; y += MAX(1, height / 12)) {
        for (int x = 0; x < width; x += MAX(1, width / 16)) {
            const guchar *pixel = pixels + y * stride + x * channels;
            if (pixel[0] + pixel[1] + pixel[2] > 18 && ++visible >= 3)
                return TRUE;
        }
    }
    return FALSE;
}

static GdkPixbuf *render_preview(Switcher *switcher, Window xid)
{
    Display *display = switcher->xdisplay;
    XWindowAttributes attributes;
    if (!XGetWindowAttributes(display, xid, &attributes) || attributes.map_state != IsViewable ||
        attributes.width < 2 || attributes.height < 2)
        return NULL;

    XRenderPictFormat *input = XRenderFindVisualFormat(display, attributes.visual);
    XRenderPictFormat *output = XRenderFindStandardFormat(display, PictStandardRGB24);
    if (!input || !output)
        return NULL;

    double ratio = MIN((double)switcher->preview_width / attributes.width, 132.0 / attributes.height);
    int width = MAX(1, (int)(attributes.width * ratio + 0.5));
    int height = MAX(1, (int)(attributes.height * ratio + 0.5));
    Pixmap backing = switcher->composite ? XCompositeNameWindowPixmap(display, xid) : None;
    Drawable drawable = backing ? backing : xid;
    Pixmap thumbnail = XCreatePixmap(display, attributes.root, width, height, output->depth);
    Picture source = XRenderCreatePicture(display, drawable, input, 0, NULL);
    Picture destination = XRenderCreatePicture(display, thumbnail, output, 0, NULL);
    XTransform transform = {{
        { XDoubleToFixed((double)attributes.width / width), 0, 0 },
        { 0, XDoubleToFixed((double)attributes.height / height), 0 },
        { 0, 0, XDoubleToFixed(1) },
    }};
    XRenderSetPictureTransform(display, source, &transform);
    XRenderSetPictureFilter(display, source, FilterBilinear, NULL, 0);
    XRenderComposite(display, PictOpSrc, source, None, destination, 0, 0, 0, 0, 0, 0, width, height);

    /* Only read back the thumbnail. XRender scales the full window on the server. */
    cairo_surface_t *surface = cairo_xlib_surface_create_with_xrender_format(
        display, thumbnail, attributes.screen, output, width, height);
    GdkPixbuf *pixbuf = gdk_pixbuf_get_from_surface(surface, 0, 0, width, height);
    cairo_surface_destroy(surface);
    XRenderFreePicture(display, destination);
    XRenderFreePicture(display, source);
    XFreePixmap(display, thumbnail);
    if (backing)
        XFreePixmap(display, backing);
    return pixbuf;
}

static gboolean capture_next(GtkWidget *widget, GdkFrameClock *clock, gpointer data)
{
    (void)widget;
    (void)clock;
    Switcher *switcher = data;
    if (switcher->first_frame) {
        switcher->first_frame = FALSE;
        return G_SOURCE_CONTINUE;
    }

    int count = (int)switcher->entries->len;
    int first_row = (int)gtk_adjustment_get_value(switcher->scroll) / (CARD_HEIGHT + GAP);
    int first = first_row * switcher->columns;
    for (int offset = 0; offset < count; offset++) {
        int index = (first + offset) % count;
        Entry *entry = &g_array_index(switcher->entries, Entry, index);
        if (entry->captured)
            continue;
        entry->captured = TRUE;
        if (!wnck_window_is_minimized(entry->client)) {
            gdk_x11_display_error_trap_push(switcher->display);
            GdkPixbuf *preview = render_preview(switcher, wnck_window_get_xid(entry->client));
            if (gdk_x11_display_error_trap_pop(switcher->display) == 0 &&
                preview && has_preview_pixels(preview))
                gtk_image_set_from_pixbuf(GTK_IMAGE(entry->image), preview);
            g_clear_object(&preview);
        }
        return G_SOURCE_CONTINUE;
    }
    return G_SOURCE_REMOVE;
}

static void select_entry(Switcher *switcher, int index)
{
    Entry *old = &g_array_index(switcher->entries, Entry, switcher->selected);
    Entry *entry = &g_array_index(switcher->entries, Entry, index);
    gtk_style_context_remove_class(gtk_widget_get_style_context(old->button), "selected");
    switcher->selected = index;
    gtk_style_context_add_class(gtk_widget_get_style_context(entry->button), "selected");
    gtk_widget_grab_focus(entry->button);
    double top = index / switcher->columns * (CARD_HEIGHT + GAP);
    gtk_adjustment_clamp_page(switcher->scroll, top, top + CARD_HEIGHT);
}

static void step(Switcher *switcher, int direction)
{
    int count = (int)switcher->entries->len;
    select_entry(switcher, (switcher->selected + direction + count) % count);
}

static void activate(Switcher *switcher, int index)
{
    if (switcher->closing)
        return;
    switcher->closing = TRUE;
    Entry *entry = &g_array_index(switcher->entries, Entry, index);
    char xid[32];
    g_snprintf(xid, sizeof(xid), "0x%lx", wnck_window_get_xid(entry->client));
    char *argv[] = { "bspc", "node", xid, "-f", NULL };
    g_spawn_sync(NULL, argv, NULL, G_SPAWN_SEARCH_PATH | G_SPAWN_STDOUT_TO_DEV_NULL |
                 G_SPAWN_STDERR_TO_DEV_NULL, NULL, NULL, NULL, NULL, NULL, NULL);
    gtk_main_quit();
}

static void clicked(GtkButton *button, gpointer data)
{
    activate(data, GPOINTER_TO_INT(g_object_get_data(G_OBJECT(button), "entry-index")));
}

static gboolean key_press(GtkWidget *window, GdkEventKey *event, gpointer data)
{
    (void)window;
    Switcher *switcher = data;
    int count = (int)switcher->entries->len;
    int index = switcher->selected;
    switch (event->keyval) {
    case GDK_KEY_Escape: gtk_main_quit(); break;
    case GDK_KEY_Return: case GDK_KEY_KP_Enter: case GDK_KEY_space: activate(switcher, index); break;
    case GDK_KEY_Left: step(switcher, -1); break;
    case GDK_KEY_Right: step(switcher, 1); break;
    case GDK_KEY_Tab: case GDK_KEY_ISO_Left_Tab:
        step(switcher, event->state & GDK_SHIFT_MASK ? -1 : 1);
        break;
    case GDK_KEY_Up:
        if (index >= switcher->columns)
            select_entry(switcher, index - switcher->columns);
        break;
    case GDK_KEY_Down:
        if (index / switcher->columns < (count - 1) / switcher->columns)
            select_entry(switcher, MIN(count - 1, index + switcher->columns));
        break;
    default: return FALSE;
    }
    return TRUE;
}

static gboolean watch_alt(gpointer data)
{
    Switcher *switcher = data;
    GdkKeymap *keymap = gdk_keymap_get_for_display(switcher->display);
    if (gdk_keymap_get_modifier_state(keymap) & GDK_MOD1_MASK)
        return G_SOURCE_CONTINUE;
    activate(switcher, switcher->selected);
    /* main() removes the source after the main loop exits. */
    return G_SOURCE_CONTINUE;
}

static gboolean close_window(GtkWidget *window, GdkEvent *event, gpointer data)
{
    (void)window;
    (void)event;
    (void)data;
    gtk_main_quit();
    return TRUE;
}

static void build_window(Switcher *switcher, gboolean previous)
{
    GtkWidget *window = switcher->window = gtk_window_new(GTK_WINDOW_TOPLEVEL);
    gtk_widget_set_name(window, "switcher-window");
    gtk_window_set_title(GTK_WINDOW(window), "Selector de ventanas");
    G_GNUC_BEGIN_IGNORE_DEPRECATIONS
    gtk_window_set_wmclass(GTK_WINDOW(window), "bspwm-window-switcher", "BspwmWindowSwitcher");
    G_GNUC_END_IGNORE_DEPRECATIONS
    gtk_window_set_decorated(GTK_WINDOW(window), FALSE);
    gtk_window_set_resizable(GTK_WINDOW(window), FALSE);
    gtk_window_set_keep_above(GTK_WINDOW(window), TRUE);
    gtk_window_set_skip_taskbar_hint(GTK_WINDOW(window), TRUE);
    gtk_window_set_skip_pager_hint(GTK_WINDOW(window), TRUE);
    gtk_window_set_type_hint(GTK_WINDOW(window), GDK_WINDOW_TYPE_HINT_DIALOG);
    gtk_window_set_position(GTK_WINDOW(window), GTK_WIN_POS_CENTER);

    GdkScreen *screen = gtk_widget_get_screen(window);
    GdkVisual *visual = gdk_screen_get_rgba_visual(screen);
    if (visual)
        gtk_widget_set_visual(window, visual);
    GtkCssProvider *provider = gtk_css_provider_new();
    gtk_css_provider_load_from_data(provider, css, -1, NULL);
    gtk_style_context_add_provider_for_screen(screen, GTK_STYLE_PROVIDER(provider),
                                               GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);
    g_object_unref(provider);

    GdkMonitor *monitor = gdk_display_get_primary_monitor(switcher->display);
    if (!monitor)
        monitor = gdk_display_get_monitor(switcher->display, 0);
    GdkRectangle area;
    gdk_monitor_get_workarea(monitor, &area);
    int count = (int)switcher->entries->len;
    switcher->columns = MIN(count, MIN(MAX_COLUMNS, MAX(1, (area.width - 40) / 200)));
    int columns = switcher->columns;
    int rows = (count + columns - 1) / columns;
    int visible_rows = MIN(rows, VISIBLE_ROWS);
    int card_width = MIN(246, MAX(1, (area.width - 56 - GAP * (columns - 1)) / columns));
    switcher->preview_width = MAX(1, card_width - 24);

    GtkWidget *outer = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);
    gtk_container_set_border_width(GTK_CONTAINER(outer), 14);
    gtk_container_add(GTK_CONTAINER(window), outer);
    GtkWidget *scroller = gtk_scrolled_window_new(NULL, NULL);
    gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(scroller), GTK_POLICY_NEVER,
                                   rows > visible_rows ? GTK_POLICY_ALWAYS : GTK_POLICY_NEVER);
    gtk_scrolled_window_set_overlay_scrolling(GTK_SCROLLED_WINDOW(scroller), FALSE);
    gtk_widget_set_size_request(scroller, columns * card_width + (columns - 1) * GAP +
                                (rows > visible_rows ? 14 : 0),
                                visible_rows * CARD_HEIGHT + (visible_rows - 1) * GAP);
    gtk_box_pack_start(GTK_BOX(outer), scroller, TRUE, TRUE, 0);
    switcher->scroll = gtk_scrolled_window_get_vadjustment(GTK_SCROLLED_WINDOW(scroller));

    GtkWidget *grid = gtk_grid_new();
    gtk_grid_set_row_spacing(GTK_GRID(grid), GAP);
    gtk_grid_set_column_spacing(GTK_GRID(grid), GAP);
    gtk_widget_set_halign(grid, GTK_ALIGN_CENTER);
    gtk_widget_set_valign(grid, GTK_ALIGN_START);
    gtk_container_add(GTK_CONTAINER(scroller), grid);

    for (int index = 0; index < count; index++) {
        Entry *entry = &g_array_index(switcher->entries, Entry, index);
        GtkWidget *button = entry->button = gtk_button_new();
        gtk_widget_set_name(button, "switcher-card");
        gtk_widget_set_size_request(button, card_width, CARD_HEIGHT);
        gtk_button_set_relief(GTK_BUTTON(button), GTK_RELIEF_NONE);
        const char *title = wnck_window_get_name(entry->client);
        atk_object_set_name(gtk_widget_get_accessible(button), title ? title : "Ventana");
        g_object_set_data(G_OBJECT(button), "entry-index", GINT_TO_POINTER(index));
        g_signal_connect(button, "clicked", G_CALLBACK(clicked), switcher);

        GtkWidget *frame = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);
        gtk_widget_set_name(frame, "preview-frame");
        gtk_widget_set_size_request(frame, switcher->preview_width + 4, 136);
        gtk_widget_set_halign(frame, GTK_ALIGN_CENTER);
        gtk_widget_set_valign(frame, GTK_ALIGN_CENTER);
        gtk_container_add(GTK_CONTAINER(button), frame);
        GdkPixbuf *icon = wnck_window_get_icon(entry->client);
        entry->image = icon ? gtk_image_new_from_pixbuf(icon) :
            gtk_image_new_from_icon_name("application-x-executable", GTK_ICON_SIZE_DIALOG);
        gtk_widget_set_halign(entry->image, GTK_ALIGN_CENTER);
        gtk_widget_set_valign(entry->image, GTK_ALIGN_CENTER);
        gtk_box_pack_start(GTK_BOX(frame), entry->image, TRUE, TRUE, 0);
        gtk_grid_attach(GTK_GRID(grid), button, index % columns, index / columns, 1, 1);
    }
    g_signal_connect(window, "delete-event", G_CALLBACK(close_window), switcher);
    g_signal_connect(window, "key-press-event", G_CALLBACK(key_press), switcher);
    gtk_widget_show_all(window);
    select_entry(switcher, previous ? count - 1 : 1 % count);
    gtk_window_present(GTK_WINDOW(window));
}

static gboolean receive_steps(int fd, GIOCondition condition, gpointer data)
{
    (void)condition;
    char command;
    while (recv(fd, &command, 1, 0) == 1) {
        if (command == '+' || command == '-')
            step(data, command == '+' ? 1 : -1);
    }
    return G_SOURCE_CONTINUE;
}

int main(int argc, char **argv)
{
    gboolean previous = FALSE, alt_held = FALSE;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--previous") == 0)
            previous = TRUE;
        else if (strcmp(argv[i], "--alt-held") == 0)
            alt_held = TRUE;
        else {
            fprintf(stderr, "Uso: window-switcher [--previous] [--alt-held]\n");
            return 2;
        }
    }

    g_autofree char *socket_path = g_build_filename(g_get_user_runtime_dir(),
                                                   "bspwm-window-switcher.sock", NULL);
    g_autofree char *lock_path = g_strconcat(socket_path, ".lock", NULL);
    struct sockaddr_un address = { .sun_family = AF_UNIX };
    if (strlen(socket_path) >= sizeof(address.sun_path)) {
        fprintf(stderr, "window-switcher: ruta del socket demasiado larga\n");
        return 1;
    }
    strcpy(address.sun_path, socket_path);
    socklen_t length = offsetof(struct sockaddr_un, sun_path) + strlen(socket_path) + 1;
    int guard = open(lock_path, O_CREAT | O_CLOEXEC | O_RDWR, 0600);
    int fd = socket(AF_UNIX, SOCK_DGRAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (guard < 0 || fd < 0) {
        perror("window-switcher");
        return 1;
    }

    /* Forward repeated Alt+Tab to the existing window without loading GTK. */
    char command = previous ? '-' : '+';
    for (int attempt = 0; flock(guard, LOCK_EX | LOCK_NB) != 0; attempt++) {
        if (errno != EWOULDBLOCK || attempt == 20) {
            perror("window-switcher: bloqueo");
            return 1;
        }
        if (sendto(fd, &command, 1, 0, (struct sockaddr *)&address, length) == 1)
            return 0;
        g_usleep(5000);
    }

    unlink(socket_path);
    if (bind(fd, (struct sockaddr *)&address, length) != 0) {
        perror("window-switcher: socket");
        return 1;
    }

    int result = 0;
    gdk_set_allowed_backends("x11");
    if (!gtk_init_check(NULL, NULL)) {
        fprintf(stderr, "window-switcher: no se pudo abrir la sesión X11\n");
        result = 1;
        goto cleanup;
    }

    WnckHandle *handle = wnck_handle_new(WNCK_CLIENT_TYPE_PAGER);
    Switcher switcher = { .display = gdk_display_get_default(), .first_frame = TRUE };
    switcher.xdisplay = gdk_x11_display_get_xdisplay(switcher.display);
    int event_base, error_base, major, minor;
    switcher.composite = gdk_screen_is_composited(gdk_display_get_default_screen(switcher.display)) &&
        XCompositeQueryExtension(switcher.xdisplay, &event_base, &error_base) &&
        XCompositeQueryVersion(switcher.xdisplay, &major, &minor) && (major > 0 || minor >= 2);
    gboolean render = XRenderQueryExtension(switcher.xdisplay, &event_base, &error_base);
    switcher.entries = g_array_new(FALSE, TRUE, sizeof(Entry));
    collect_windows(&switcher, wnck_handle_get_default_screen(handle));
    if (switcher.entries->len) {
        build_window(&switcher, previous);
        guint commands = g_unix_fd_add(fd, G_IO_IN, receive_steps, &switcher);
        guint release = alt_held ? g_timeout_add(16, watch_alt, &switcher) : 0;
        if (render)
            gtk_widget_add_tick_callback(switcher.window, capture_next, &switcher, NULL);
        gtk_main();
        g_source_remove(commands);
        if (release)
            g_source_remove(release);
        gtk_widget_destroy(switcher.window);
    }
    for (guint i = 0; i < switcher.entries->len; i++)
        g_object_unref(g_array_index(switcher.entries, Entry, i).client);
    g_array_unref(switcher.entries);
    g_object_unref(handle);

cleanup:
    unlink(socket_path);
    close(fd);
    close(guard);
    return result;
}
