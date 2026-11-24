#define _GNU_SOURCE
#include <dlfcn.h>
#include <stddef.h>

/* Nautilus 48 leaves enough room for only three very wide columns. Interpose
 * the GTK constructor inside Nautilus and request four columns instead. The
 * opaque declarations keep this helper independent of GTK development files. */
typedef void *(*GtkGridViewNew)(void *model, void *factory);
typedef void (*GtkGridViewSetMinColumns)(void *view, unsigned int columns);

void *
gtk_grid_view_new (void *model,
                   void *factory)
{
    static GtkGridViewNew real_new;
    static GtkGridViewSetMinColumns set_min_columns;
    void *view;

    if (real_new == NULL)
    {
        real_new = (GtkGridViewNew) dlsym (RTLD_NEXT, "gtk_grid_view_new");
        set_min_columns = (GtkGridViewSetMinColumns) dlsym (RTLD_NEXT,
                                                            "gtk_grid_view_set_min_columns");
    }

    if (real_new == NULL)
    {
        return NULL;
    }

    view = real_new (model, factory);
    if (view != NULL && set_min_columns != NULL)
    {
        set_min_columns (view, 4);
    }

    return view;
}
