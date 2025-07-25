import numpy as np

import astropy.units as u
from astropy.wcs.utils import pixel_to_pixel
from astropy.visualization import ImageNormalize, LinearStretch, PercentileInterval
from glue.core.link_helpers import LinkSame
from glue_jupyter.bqplot.image import BqplotImageView

from jdaviz.configs.imviz import wcs_utils
from jdaviz.configs.default import aida
from jdaviz.core.astrowidgets_api import AstrowidgetsImageViewerMixin
from jdaviz.core.events import SnackbarMessage
from jdaviz.core.registries import viewer_registry
from jdaviz.core.freezable_state import FreezableBqplotImageViewerState
from jdaviz.configs.default.plugins.viewers import JdavizViewerMixin
from jdaviz.utils import (get_wcs_only_layer_labels, data_has_valid_wcs,
                          layer_is_image_data, get_top_layer_index)

__all__ = ['ImvizImageView']


@viewer_registry("imviz-image-viewer", label="Image 2D (Imviz)")
class ImvizImageView(JdavizViewerMixin, BqplotImageView, AstrowidgetsImageViewerMixin):
    # categories: zoom resets, zoom, pan, subset, select tools, shortcuts
    tools_nested = [
                    ['jdaviz:homezoom', 'jdaviz:prevzoom'],
                    ['jdaviz:boxzoommatch', 'jdaviz:boxzoom'],
                    ['jdaviz:panzoommatch', 'jdaviz:imagepanzoom'],
                    ['bqplot:truecircle', 'bqplot:rectangle', 'bqplot:ellipse',
                     'bqplot:circannulus'],
                    ['jdaviz:blinkonce', 'jdaviz:contrastbias',
                        'jdaviz:selectcatalog', 'jdaviz:selectfootprint'],
                    ['jdaviz:sidebar_plot', 'jdaviz:sidebar_export', 'jdaviz:sidebar_compass']
                ]

    default_class = None
    _state_cls = FreezableBqplotImageViewerState

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # provide reference from state back to viewer to use for zoom syncing
        self.state._set_viewer(self)
        self.init_astrowidgets_api()
        self._subscribe_to_layers_update()

        self.compass = None
        self.line_profile_xy = None

        self.add_event_callback(self.on_mouse_or_key_event, events=['keydown'])
        self.state.add_callback('x_min', self.on_limits_change)
        self.state.add_callback('x_max', self.on_limits_change)
        self.state.add_callback('y_min', self.on_limits_change)
        self.state.add_callback('y_max', self.on_limits_change)

        self.state.show_axes = False
        self.figure.fig_margin = {'left': 0, 'bottom': 0, 'top': 0, 'right': 0}

        # By default, glue computes a fixed resolution buffer that matches the
        # axes - but this means that when panning, one sees white outside of
        # the original buffer until the buffer updates again, thus there is a
        # lag in the image display. By increasing the external padding to 0.5
        # the image is made larger by 50% along all four sides, helping create
        # the illusion of smooth panning. We can increase this further to
        # improve the panning experience, but this can cause a larger delay
        # when the image does need to update as it will be more computationally
        # intensive.
        self.state.image_external_padding = 0.5

        self.data_menu._obj.dataset.add_filter('is_image')
        self.aid = aida.AID(self)

    def on_mouse_or_key_event(self, data):
        active_image_layer = self.active_image_layer
        if active_image_layer is None:
            return

        if self.line_profile_xy is None:
            try:
                self.line_profile_xy = self.session.jdaviz_app.get_tray_item_from_name(
                    'imviz-line-profile-xy')
            except KeyError:  # pragma: no cover
                return

        if data['event'] == 'keydown':
            key_pressed = data['key']

            if key_pressed in ('b', 'B'):
                self.blink_once(reversed=key_pressed == 'B')

    def blink_once(self, reversed=False):
        # Simple blinking of images - this will make it so that only one
        # layer is visible at a time and cycles through the layers.

        # Exclude Subsets (they are global) and children via associated data

        def is_parent(data):
            return self.session.jdaviz_app._get_assoc_data_parent(data.label) is None

        valid = [ilayer for ilayer, layer in enumerate(self.state.layers)
                 if layer_is_image_data(layer.layer) and is_parent(layer.layer)]
        children = [ilayer for ilayer, layer in enumerate(self.state.layers)
                    if layer_is_image_data(layer.layer) and not is_parent(layer.layer)]

        n_layers = len(valid)

        if n_layers == 1:
            msg = SnackbarMessage(
                'Nothing to blink. Select a second image in the Data menu to use this feature.',
                color='warning', sender=self)
            self.session.hub.broadcast(msg)

        elif n_layers > 1:
            # If only one layer is visible, pick the next one to be visible,
            # otherwise start from the last visible one.

            visible = [ilayer for ilayer in valid if self.state.layers[ilayer].visible]
            n_visible = len(visible)

            if n_visible == 0:
                msg = SnackbarMessage('No visible layer to blink',
                                      color='warning', sender=self)
                self.session.hub.broadcast(msg)
            elif n_visible > 0:
                if not reversed:
                    delta = 1
                else:
                    delta = -1
                next_layer = valid[(valid.index(visible[-1]) + delta) % n_layers]
                self.state.layers[next_layer].visible = True

                # make invisible all parent layers other than the next layer:
                layers_to_set_not_visible = set(valid) - set([next_layer])
                # no child layers are visible by default:
                layers_to_set_not_visible.update(set(children))

                for ilayer in layers_to_set_not_visible:
                    self.state.layers[ilayer].visible = False

                # We can display the active data label in Compass plugin.
                self.set_compass(self.state.layers[next_layer].layer)

                # Update line profile plots too.
                if self.line_profile_xy is None:
                    try:
                        self.line_profile_xy = self.session.jdaviz_app.get_tray_item_from_name(
                            'imviz-line-profile-xy')
                    except KeyError:  # pragma: no cover
                        return
                self.line_profile_xy.viewer_selected = self.reference_id
                self.line_profile_xy.vue_draw_plot()

    def on_limits_change(self, *args):
        try:
            i = get_top_layer_index(self)
        except IndexError:
            if self.compass is not None:
                self.compass.clear_compass()
            return
        if i is None:
            return
        self.set_compass(self.state.layers[i].layer)

    @property
    def top_visible_data_label(self):
        """Data label of the top visible layer in the viewer."""
        try:
            i = get_top_layer_index(self)
        except IndexError:
            data_label = ''
        else:
            if i is None:
                data_label = ''
            else:
                data_label = self.state.layers[i].layer.label
        return data_label

    @property
    def first_loaded_data(self):
        """Data that is first loaded into the viewer.
        This may not be the visible layer.
        Returns `None` if no real data is loaded.
        """
        for lyr in self.layers:
            data = lyr.layer
            if layer_is_image_data(data):
                return data

    def _get_real_xy(self, image, x, y, reverse=False):
        """Return real (X, Y) position and status in case of dithering as well as whether the
        results were within the bounding box of the reference data or required possibly inaccurate
        extrapolation.

        ``coords_status`` is for ``CoordsInfo`` coords handling only.
        When `True`, it sets the coords, otherwise it resets.

        ``reverse=True`` is only for internal roundtripping (e.g., centroiding
        in Subset Tools plugin). Never use this for coordinates display panel.

        """
        # By default we'll assume the coordinates are valid and within any applicable bounding box.
        unreliable_world = False
        unreliable_pixel = False
        if data_has_valid_wcs(image):
            # Convert these to a SkyCoord via WCS - note that for other datasets
            # we aren't actually guaranteed to get a SkyCoord out, just for images
            # with valid celestial WCS
            try:
                align_by = self.get_alignment_method(image.label).lower()

                # Convert X,Y from reference data to the one we are actually seeing.
                # world_to_pixel return scalar ndarray that we need to convert to float.
                if align_by == 'wcs':
                    if not reverse:
                        # Convert X,Y from reference data to the one we are actually seeing.

                        x_image_coords, y_image_coords = list(map(float, pixel_to_pixel(
                            self.state.reference_data.coords, image.coords, x, y)))
                        outside_image_bounding_box = wcs_utils.data_outside_gwcs_bounding_box(
                            image, x_image_coords, y_image_coords)

                        if outside_image_bounding_box:
                            # coordinates outside the bounding box are unreliable
                            unreliable_pixel = unreliable_world = True
                        else:
                            x, y = x_image_coords, y_image_coords
                            # any coordinate inside the bounding box should be reliable
                            unreliable_pixel = unreliable_world = False

                    else:
                        # We don't bother with unreliable_pixel and unreliable_world computation
                        # because this takes input (x, y) in the frame of visible layer and wants
                        # to convert it back to the frame of reference layer to pass back to the
                        # viewer. At this point, we no longer know if input (x, y) is accurate
                        # or not.
                        x, y = list(map(float, pixel_to_pixel(
                            image.coords, self.state.reference_data.coords, x, y)))
                else:  # pixels or self
                    unreliable_world = wcs_utils.data_outside_gwcs_bounding_box(image, x, y)

                coords_status = True
            except Exception:
                coords_status = False
        else:
            coords_status = False

        return x, y, coords_status, (unreliable_world, unreliable_pixel)

    def _get_zoom_limits(self, image):
        """Return a list of ``(x, y)`` that defines four corners of
        the zoom box for a given image.
        This is needed because viewer values are only based on reference
        image, which can be inaccurate if given image is dithered and
        they are linked by WCS.
        """
        if self.state.reference_data.meta.get('_WCS_ONLY', False):
            corner_world_coords = self.state.reference_data.coords.pixel_to_world(
                (self.state.x_min, self.state.x_min, self.state.x_max, self.state.x_max),
                (self.state.y_min, self.state.y_max, self.state.y_max, self.state.y_min)
            )
            # Convert X,Y from reference data to the one we are actually seeing.
            x = image.coords.world_to_pixel(corner_world_coords)
            zoom_limits = np.array(list(zip(x[0], x[1])))
        else:
            zoom_limits = np.array(((self.state.x_min, self.state.y_min),
                                    (self.state.x_min, self.state.y_max),
                                    (self.state.x_max, self.state.y_max),
                                    (self.state.x_max, self.state.y_min)))

        return zoom_limits

    def set_compass(self, image):
        """Update the Compass plugin with info from the given image Data object."""
        if self.compass is None:  # Maybe another viewer has it
            return

        zoom_limits = self._get_zoom_limits(image)

        # Downsample input data to about 400px (as per compass.vue) for performance.
        xstep = max(1, round(image.shape[1] / 400))
        ystep = max(1, round(image.shape[0] / 400))
        arr = image[image.main_components[0]][::ystep, ::xstep]
        vmin, vmax = PercentileInterval(95).get_limits(arr)
        norm = ImageNormalize(vmin=vmin, vmax=vmax, stretch=LinearStretch())
        self.compass.draw_compass(image.label, wcs_utils.draw_compass_mpl(
            arr, orig_shape=image.shape, wcs=image.coords, show=False, zoom_limits=zoom_limits,
            norm=norm))

    def set_plot_axes(self):
        self.figure.axes[1].tick_format = None
        self.figure.axes[0].tick_format = None

        self.figure.axes[1].label = "y: pixels"
        self.figure.axes[0].label = "x: pixels"

        # Make it so y axis label is not covering tick numbers.
        self.figure.axes[1].label_offset = "-50"

    def data(self, cls=None):
        return [layer_state.layer  # .get_object(cls=cls or self.default_class)
                for layer_state in self.state.layers
                if hasattr(layer_state, 'layer') and
                layer_is_image_data(layer_state.layer)]

    def get_alignment_method(self, data_label):
        """Find the type of ``glue`` linking between the given
        data label with the reference data in viewer.

        Parameters
        ----------
        data_label : str
            Data label to look up.

        Returns
        -------
        align_by : {'pixels', 'wcs', 'self'}
            One of the link types accepted by the Orientation plugin
            or ``'self'`` if the data label belongs to the reference data itself.

        Raises
        ------
        ValueError
            Link look-up failed.

        """
        if len(self.session.application.data_collection) == 0:
            raise ValueError('No reference data for link look-up')

        ref_label = getattr(self.state.reference_data, 'label', None)
        if data_label == ref_label:
            return 'self'

        if ref_label in get_wcs_only_layer_labels(self.jdaviz_app):
            return 'wcs'

        align_by = None
        for elink in self.session.application.data_collection.external_links:
            elink_labels = (elink.data1.label, elink.data2.label)
            if data_label in elink_labels and ref_label in elink_labels:
                if isinstance(elink, LinkSame):  # Assumes WCS link never uses LinkSame
                    align_by = 'pixels'
                else:  # If not pixels, must be WCS
                    align_by = 'wcs'
                break  # Might have duplicate, just grab first match

        if align_by is None:
            raise ValueError(f'{data_label} not found in data collection external links')

        return align_by

    def _get_fov(self, wcs=None):
        if wcs is None:
            wcs = self.state.reference_data.coords
        if self.jdaviz_app._align_by != "wcs" or wcs is None:
            return

        # compute the mean of the height and width of the
        # viewer's FOV on ``data`` in world units:
        x_corners = [
            self.state.x_min,
            self.state.x_max,
            self.state.x_min
        ]
        y_corners = [
            self.state.y_min,
            self.state.y_min,
            self.state.y_max
        ]

        sky_corners = wcs.pixel_to_world(x_corners, y_corners)
        height_sky = abs(sky_corners[0].separation(sky_corners[2]))
        width_sky = abs(sky_corners[0].separation(sky_corners[1]))
        fov_sky = u.Quantity([height_sky, width_sky]).mean()
        return fov_sky

    def _get_center_skycoord(self, data=None):
        # get SkyCoord for the center of ``data`` in this viewer:
        x_cen = (self.state.x_min + self.state.x_max) * 0.5
        y_cen = (self.state.y_min + self.state.y_max) * 0.5

        if (self.jdaviz_app._align_by == "wcs" or data is None
                or data.label == self.state.reference_data.label):
            return self.state.reference_data.coords.pixel_to_world(x_cen, y_cen)

        if data.coords is not None:
            return data.coords.pixel_to_world(x_cen, y_cen)
