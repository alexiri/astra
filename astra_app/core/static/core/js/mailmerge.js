(function (window, document) {
  'use strict';

  function $(id) {
    return document.getElementById(id);
  }

  function setAction(value) {
    var el = $('mailmerge-action');
    if (el) el.value = value;
  }

  function getCompose() {
    return window.TemplatedEmailCompose || null;
  }

  function syncRecipientModeFromAccordion() {
    var modeEl = $('mailmerge-recipient-mode');
    if (!modeEl) return;

    var groupPanel = $('mailmerge-collapse-group');
    var csvPanel = $('mailmerge-collapse-csv');

    var groupOpen = !!(groupPanel && groupPanel.classList && groupPanel.classList.contains('show'));
    var csvOpen = !!(csvPanel && csvPanel.classList && csvPanel.classList.contains('show'));

    if (groupOpen && !csvOpen) {
      modeEl.value = 'group';
      return;
    }

    if (csvOpen && !groupOpen) {
      modeEl.value = 'csv';
      return;
    }

    // Fallback if accordion is in an unexpected state.
    modeEl.value = '';
  }

  function hideRecipientsWarning() {
    var box = $('mailmerge-recipients-inline-warning');
    if (!box) return;
    box.classList.add('d-none');
    box.textContent = '';
  }

  function showRecipientsWarning(message) {
    var box = $('mailmerge-recipients-inline-warning');
    if (!box) return;
    box.textContent = String(message || '');
    box.classList.remove('d-none');
  }

  function hasSavedCsvRecipients() {
    var el = $('mailmerge-has-saved-csv');
    return !!(el && String(el.value || '') === '1');
  }

  function validateRecipientsBeforeSubmit(evt) {
    hideRecipientsWarning();
    syncRecipientModeFromAccordion();

    var modeEl = $('mailmerge-recipient-mode');
    var mode = modeEl ? String(modeEl.value || '').trim() : '';

    if (mode === 'group') {
      var groupSelected = String(getField('id_group_cn') || '').trim() !== '';
      if (!groupSelected) {
        if (evt && evt.preventDefault) evt.preventDefault();
        showRecipientsWarning('Select a group, or switch to CSV recipients.');
        return false;
      }
      return true;
    }

    if (mode === 'csv') {
      var csvEl = $('id_csv_file');
      var csvSelected = false;
      if (csvEl) {
        if (csvEl.files && csvEl.files.length > 0) {
          csvSelected = true;
        } else {
          csvSelected = String(csvEl.value || '').trim() !== '';
        }
      }

      if (!csvSelected && !hasSavedCsvRecipients()) {
        if (evt && evt.preventDefault) evt.preventDefault();
        showRecipientsWarning('Upload a CSV, or switch to Group recipients.');
        return false;
      }

      return true;
    }

    if (evt && evt.preventDefault) evt.preventDefault();
    showRecipientsWarning('Choose Group or CSV recipients first.');
    return false;
  }

  function onReady() {
    document.addEventListener('templated-email-compose:save-confirmed', function () {
      setAction('save');
      var form = $('mailmerge-form');
      if (form) form.submit();
    });

    document.addEventListener('templated-email-compose:save-as-confirmed', function (e) {
      var detail = e && e.detail ? e.detail : {};
      var name = String((detail && detail.name) || '').trim();
      if (!name) return;
      $('mailmerge-save-as-name').value = name;
      setAction('save_as');
      var form = $('mailmerge-form');
      if (form) form.submit();
    });

    var composeBindingsReady = false;

    function bindComposeOnceReady() {
      if (composeBindingsReady) return;

      var compose = getCompose();
      if (!compose) {
        window.setTimeout(bindComposeOnceReady, 25);
        return;
      }

      composeBindingsReady = true;

      var templateSelect = compose.getTemplateSelectEl ? compose.getTemplateSelectEl() : null;

      // After a successful "Save as", the server re-renders with the new template
      // selected. The form fields already contain the correct content, so we only
      // need to set Restore/baseline so the user can start editing immediately.
      var autoloadEl = $('mailmerge-autoload-template-id');
      if (autoloadEl) {
        var autoloadId = String(autoloadEl.value || '').trim();
        if (autoloadId) {
          if (compose.setTemplateId) {
            compose.setTemplateId(autoloadId);
          } else if (templateSelect) {
            templateSelect.value = autoloadId;
          }

          // Do NOT refetch the template JSON here: it would be async and could
          // overwrite edits if the user starts typing quickly.
          compose.setRestoreEnabled(true);
          compose.markBaseline(compose.getValues());
          if (window.TemplatedEmailComposePreview) {
            window.TemplatedEmailComposePreview.schedulePreviewRefresh(compose, 0);
          }
        }
      }
    }

    bindComposeOnceReady();

    // Note: the compose widget dispatches templated-email-compose:content-updated,
    // and we refresh preview off that signal.

    // Keep recipient_mode in sync with the accordion selection.
    var groupPanel = $('mailmerge-collapse-group');
    if (groupPanel) {
      groupPanel.addEventListener('shown.bs.collapse', syncRecipientModeFromAccordion);
      groupPanel.addEventListener('hidden.bs.collapse', syncRecipientModeFromAccordion);
      groupPanel.addEventListener('shown.bs.collapse', hideRecipientsWarning);
      groupPanel.addEventListener('hidden.bs.collapse', hideRecipientsWarning);
    }
    var csvPanel = $('mailmerge-collapse-csv');
    if (csvPanel) {
      csvPanel.addEventListener('shown.bs.collapse', syncRecipientModeFromAccordion);
      csvPanel.addEventListener('hidden.bs.collapse', syncRecipientModeFromAccordion);
      csvPanel.addEventListener('shown.bs.collapse', hideRecipientsWarning);
      csvPanel.addEventListener('hidden.bs.collapse', hideRecipientsWarning);
    }

    var loadBtn = $('mailmerge-load-recipients-btn');
    if (loadBtn) {
      loadBtn.addEventListener('click', validateRecipientsBeforeSubmit);
    }

    var groupEl = $('id_group_cn');
    if (groupEl) {
      groupEl.addEventListener('change', hideRecipientsWarning);
    }

    var csvEl = $('id_csv_file');
    if (csvEl) {
      csvEl.addEventListener('change', hideRecipientsWarning);
    }

    syncRecipientModeFromAccordion();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', onReady);
  } else {
    onReady();
  }
})(window, document);
