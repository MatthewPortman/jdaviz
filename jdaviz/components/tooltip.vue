<template>
  <v-tooltip v-if="getTooltipHtml()" bottom :open-delay="getOpenDelay()"
      :nudge-bottom="getNudgeBottom()">
    <template v-slot:activator="{ on, attrs }">
      <span v-bind="attrs" v-on="on" :style="getSpanStyle()">
        <slot></slot>
      </span>
    </template>
    <span v-html="getTooltipHtml()"></span>
  </v-tooltip>
  <span v-else :style="getSpanStyle()">
    <!-- in the case where there is no tooltip, just pass through the wrapped element -->
    <slot></slot>
  </span>
</template>

<script>
// define all tooltip content here.  Each key can be passed as tipid to
// any j-tooltip element.  The values must be a string, but can contain (valid)
// html.  If enabling a new tooltip, wrap the element in <j-tooltip tipid='...'>,
// pass doctips from state/props, and test to make sure layout isn't adversely
// affected by the wrapping divs.
const tooltips = {
  // app toolbar
  'app-help': 'Open docs in new tab',
  'app-api-hints': 'Toggle API hints',
  'app-toolbar-logger-configged': 'Toggle displaying logger in sidebar tray',  // non-deconfigged only
  'app-toolbar-plugins-configged': 'Toggle displaying plugins in sidebar tray',  // non-deconfigged only
  'app-toolbar-loaders': 'Add data or viewers',
  'app-toolbar-settings': 'Settings and options',
  'app-toolbar-save': 'Export data, viewers, tables',
  'app-toolbar-subsets': 'View and edit subsets',
  'app-toolbar-info': 'Metadata, mouseover markers, and logger',
  'app-toolbar-plugins': 'Data analysis plugins',
  'app-toolbar-popout': `Display in a new window<br /><br />
    <div style="width: 200px; border: 1px solid gray;" class="pa-2">
      <strong>Note:</strong>
      some ad blockers or browser settings may block popup windows,
      causing this feature not to work.
    </div>`,
  'plugin-api-hints': 'Toggle displaying inline API hints',
  'plugin-popout': `Display in a new window<br /><br />
    <div style="width: 200px; border: 1px solid gray;" class="pa-2">
      <strong>Note:</strong>
      some ad blockers or browser settings may block popup windows,
      causing this feature not to work.
    </div>`,

  'g-data-tools':
    'Load data from file',
  'g-viewer-creator':
     'Create a new viewer',
  'g-subset-tools':
    'Select, create, and delete subsets',
  'g-subset-mode':
    'Operation performed by subset selection in viewer',
  'g-unified-slider':
    'Grab slider to slice through cube or select slice number',
  'g-redshift-slider':
    'Move the slider to change the redshift of the source and line wavelengths',
  'lock-row-toggle':
    'Use the same display parameters for all images and spectra',
  'create-image-viewer':
    'Create new image viewer',
  'coords-info-cycle': 'Cycle selected layer used for mouseover information and markers plugin',

  // viewer toolbars
  'viewer-toolbar-data': 'Select dataset(s) to display in this viewer',
  'viewer-toolbar-figure': 'Tools: pan, zoom, select region, save',
  'viewer-toolbar-figure-save': 'Save figure',
  'viewer-toolbar-menu': 'Adjust display: contrast, bias, stretch',
  'viewer-toolbar-more': 'More options...',

  'table-prev': 'Select previous row in table',
  'table-next': 'Select next row in table',
  'table-play-pause-toggle': 'Toggle cycling through rows of table',
  'table-play-pause-delay': 'Set delay before cycling to next entry',
  'viewer-multiselect-toggle': 'Toggle between choosing a single or multiple viewer(s)',
  'layer-multiselect-toggle': 'Toggle between choosing a single or multiple layer(s)',
  'plugin-plot-options-mixed-state': 'Current values are mixed, click to sync at shown value',
  'plugin-model-fitting-add-model': 'Create model component',
  'plugin-model-fitting-param-fixed': 'Check the box to freeze parameter value',
  'plugin-model-fitting-reestimate-all': 'Re-estimate initial values based on the current data/subset selection for all free parameters based on current display units',
  'plugin-model-fitting-reestimate': 'Re-estimate initial values based on the current data/subset selection for all free parameters in this component',
  'plugin-unit-conversion-apply': 'Apply unit conversion',
  'plugin-line-lists-load': 'Load list into "Loaded Lines" section of plugin',
  'plugin-line-lists-plot-all-in-list': 'Plot all lines in this list',
  'plugin-line-lists-erase-all-in-list': 'Hide all lines in this list',
  'plugin-line-lists-plot-all': 'Plot all lines from every loaded list',
  'plugin-line-lists-erase-all': 'Hide all lines from every loaded list',
  'plugin-line-lists-line-name': 'Name this whatever you want',
  'plugin-line-lists-custom-rest': 'This is a float or integer',
  'plugin-line-lists-add-custom-line': 'Add line to the custom list',
  'plugin-line-lists-line-identify-chip-active': 'Currently highlighted line.  Click to clear current selection.',
  'plugin-line-lists-line-identify-chip-inactive': 'No line currently highlighted.  Use selection tool in spectrum viewer to identify a line.',
  'plugin-line-lists-line-visible': 'Toggle showing the line in the spectrum viewer',
  'plugin-line-lists-line-identify': 'Highlight this line in the spectrum viewer for easy identification',
  'plugin-line-lists-color-picker': 'Change the color of this list',
  'plugin-line-lists-spectral-range': 'Toggle filter to only lines observable within the range of the Spectrum Viewer',
  'plugin-line-analysis-sync-identify': 'Lock/unlock selection with identified line',
  'plugin-line-analysis-assign': 'Assign the centroid wavelength and update the redshift',
  'plugin-extract-save-fits': 'Save spectral extraction as FITS file',
  'plugin-link-apply': 'Apply linking to data',
  'plugin-footprints-color-picker': 'Change the color of the footprint overlay',
  'plugin-dq-show-all': 'Show all quality flags',
  'plugin-dq-hide-all': 'Hide all quality flags',
  'plugin-dq-color-picker': 'Change the color of this DQ flag',
  'plugin-vo-refresh-resources': 'Search for available resources based on above constraints',
  'plugin-vo-autocenter-centered': 'Viewer is currently centered on these coordinates',
  'plugin-vo-autocenter-not-centered': 'Click to update coordinates to viewer\'s center',
  'plugin-vo-filter-coverage': `Only show surveys that report coverage within radius of coordinates.<br />Queries may take longer to process.<br /><br />
    <div style="border: 1px solid gray; max-width: 400px;" class="pa-2">
      <strong>Note:</strong>
      Surveys which have not implemented coverage information will also be excluded. If you are expecting a survey that doesn't appear, try disabling coverage filtering.
    </div>`
}


module.exports = {
  props: ['tooltipcontent', 'tipid', 'delay', 'nudgebottom', 'span_style'],
  methods: {
    getTooltipHtml() {
      // use tooltipcontent if provided, default to tooltips dictionary
      // with passed tipid as the key

      if (this.$props.tooltipcontent) {
        return this.$props.tooltipcontent;
      }

      // Enable the following line to help determine ids to add to dictionary
      // above.  This will show the tooltip id (in the tooltip) if no entry is
      // in the tooltips dictionary above.
      //return tooltips[this.$props.tipid] || "tipid: "+this.$props.tipid;
      return tooltips[this.$props.tipid];
    },
    getSpanStyle() {
      return this.$props.span_style || "height: inherit; display: inherit; cursor: default";
    },
    getOpenDelay() {
      return this.$props.delay || "0";
    },
    getNudgeBottom() {
      // useful for cases where some tooltips in a toolbar are wrapped around
      // buttons but others around just the icon.  Only applies to tooltip,
      // not doctip.
      return this.$props.nudgebottom || 0;
    },
  }
};
</script>
