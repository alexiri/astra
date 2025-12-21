(function () {
  function getJquery() {
    if (window.django && window.django.jQuery) {
      return window.django.jQuery;
    }
    if (window.jQuery) {
      return window.jQuery;
    }
    return null;
  }

  function init($) {
    if (!$ || !$.fn || !$.fn.bootstrapDualListbox) return;

    $('select.alx-duallistbox[multiple]').each(function () {
      var $select = $(this);

      // Avoid double-init if the admin redraws the form.
      if ($select.data('alx-duallistbox-initialized')) return;
      $select.data('alx-duallistbox-initialized', true);

      $select.bootstrapDualListbox({
        nonSelectedListLabel: 'Available',
        selectedListLabel: 'Selected',
        preserveSelectionOnMove: 'moved',
        moveOnSelect: false,
        showFilterInputs: true,
        filterPlaceHolder: 'Filter',
        filterTextClear: 'show all',
        btnClass: 'btn-outline-secondary btn-sm',
        selectorMinimalHeight: 160
      });
    });
  }

  var $ = getJquery();
  if ($) {
    $(function () {
      init($);
    });
  } else {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function () {
        init(getJquery());
      });
    } else {
      init(getJquery());
    }
  }
})();
