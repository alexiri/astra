(function (window, document) {
  'use strict';

  function $(id) {
    return document.getElementById(id);
  }

  function setAction(value) {
    var el = $('mailmerge-action');
    if (el) el.value = value;
  }

  function enable(el, on) {
    if (!el) return;
    el.disabled = !on;
  }

  function setField(id, value) {
    var el = $(id);
    if (!el) return;
    el.value = value == null ? '' : String(value);
  }

  function getField(id) {
    var el = $(id);
    if (!el) return '';
    return String(el.value || '');
  }

  function storeOriginals(payload) {
    var form = $('mailmerge-form');
    if (!form) return;

    form.dataset.originalSubject = payload.subject || '';
    form.dataset.originalHtml = payload.html_content || '';
    form.dataset.originalText = payload.text_content || '';

    enable($('mailmerge-restore-btn'), true);
  }

  function getCsrfToken() {
    var el = document.querySelector('input[name=csrfmiddlewaretoken]');
    return el ? String(el.value || '') : '';
  }

  var previewTimer = null;

  function setPreviewHtml(html) {
    var box = $('mailmerge-preview-html');
    if (!box) return;
    box.innerHTML = html || '<span class="text-muted">No preview yet.</span>';
  }

  function setPreviewText(text) {
    var box = $('mailmerge-preview-text');
    if (!box) return;
    box.textContent = text || 'No preview yet.';
  }

  async function refreshPreview() {
    var form = $('mailmerge-form');
    if (!form) return;

    var data = new window.FormData();
    data.append('subject', getField('id_subject'));
    data.append('html_content', getField('id_html_content'));
    data.append('text_content', getField('id_text_content'));

    try {
      var resp = await window.fetch('/email-tools/mail-merge/render-preview/', {
        method: 'POST',
        headers: { 'X-CSRFToken': getCsrfToken(), 'Accept': 'application/json' },
        body: data
      });

      var payload = await resp.json();
      if (!resp.ok) {
        // Keep existing previews; show a minimal hint.
        if (payload && payload.error) {
          setPreviewText(payload.error);
        }
        return;
      }

      setPreviewHtml(payload.html);
      setPreviewText(payload.text);
    } catch (_e) {
      // Ignore transient preview failures.
    }
  }

  function schedulePreviewRefresh() {
    if (previewTimer) {
      window.clearTimeout(previewTimer);
    }
    previewTimer = window.setTimeout(refreshPreview, 200);
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

  function restoreOriginals() {
    var form = $('mailmerge-form');
    if (!form) return;

    setField('id_subject', form.dataset.originalSubject || '');
    setField('id_html_content', form.dataset.originalHtml || '');
    setField('id_text_content', form.dataset.originalText || '');

    schedulePreviewRefresh();
  }

  async function loadTemplate(templateId) {
    if (!templateId) return;

    try {
      var url = '/email-tools/templates/' + encodeURIComponent(templateId) + '/json/';
      var resp = await window.fetch(url, { headers: { 'Accept': 'application/json' } });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      var payload = await resp.json();

      setField('id_subject', payload.subject);
      setField('id_html_content', payload.html_content);
      setField('id_text_content', payload.text_content);
      storeOriginals(payload);
      schedulePreviewRefresh();
    } catch (e) {
      // Fall back to server-rendered messages.
      try { window.alert('Failed to load template.'); } catch (_e) { /* noop */ }
    }
  }

  function onReady() {
    var templateSelect = $('id_email_template_id');
    if (templateSelect) {
      templateSelect.addEventListener('change', function () {
        var id = String(templateSelect.value || '').trim();
        if (!id) return;
        loadTemplate(id);
      });
    }

    var restoreBtn = $('mailmerge-restore-btn');
    if (restoreBtn) {
      restoreBtn.addEventListener('click', function (e) {
        e.preventDefault();
        restoreOriginals();
      });
    }

    var saveBtn = $('mailmerge-save-btn');
    if (saveBtn) {
      saveBtn.addEventListener('click', function (e) {
        e.preventDefault();
        var jq = window.jQuery;
        if (jq && jq.fn && typeof jq.fn.modal === 'function') {
          jq('#templated-email-save-modal').modal('show');
          return;
        }

        // Fallback if Bootstrap modal isn't available.
        var ok = false;
        try {
          ok = window.confirm('Overwrite the selected email template with the current subject and contents?');
        } catch (_e) {
          ok = false;
        }
        if (!ok) return;
        setAction('save');
        var form = $('mailmerge-form');
        if (form) form.submit();
      });
    }

    var saveAsBtn = $('mailmerge-save-as-btn');
    if (saveAsBtn) {
      saveAsBtn.addEventListener('click', function (e) {
        e.preventDefault();
        var jq = window.jQuery;
        if (jq && jq.fn && typeof jq.fn.modal === 'function') {
          var nameEl = $('templated-email-save-as-name');
          if (nameEl) nameEl.value = '';
          jq('#templated-email-save-as-modal').modal('show');
          try {
            jq('#templated-email-save-as-modal').one('shown.bs.modal', function () {
              var el = document.getElementById('templated-email-save-as-name');
              if (el && el.focus) el.focus();
            });
          } catch (_e) {
            // Ignore.
          }
          return;
        }

        // Fallback if Bootstrap modal isn't available.
        var name = '';
        try {
          name = String(window.prompt('New template name:') || '').trim();
        } catch (_e) {
          name = '';
        }
        if (!name) return;
        $('mailmerge-save-as-name').value = name;
        setAction('save_as');
        var form = $('mailmerge-form');
        if (form) form.submit();
      });
    }

    // Wire modal confirm forms.
    var saveModal = $('templated-email-save-modal');
    if (saveModal) {
      var formEl = saveModal.querySelector('form');
      if (formEl) {
        formEl.addEventListener('submit', function (e) {
          e.preventDefault();
          var jq = window.jQuery;
          if (jq && jq.fn && typeof jq.fn.modal === 'function') jq('#templated-email-save-modal').modal('hide');
          setAction('save');
          var form = $('mailmerge-form');
          if (form) form.submit();
        });
      }
    }

    var saveAsModal = $('templated-email-save-as-modal');
    if (saveAsModal) {
      var formEl2 = saveAsModal.querySelector('form');
      if (formEl2) {
        formEl2.addEventListener('submit', function (e) {
          e.preventDefault();
          var nameEl = $('templated-email-save-as-name');
          var name = nameEl ? String(nameEl.value || '').trim() : '';
          if (!name) return;
          $('mailmerge-save-as-name').value = name;
          var jq = window.jQuery;
          if (jq && jq.fn && typeof jq.fn.modal === 'function') jq('#templated-email-save-as-modal').modal('hide');
          setAction('save_as');
          var form = $('mailmerge-form');
          if (form) form.submit();
        });
      }
    }

    var htmlEl = $('id_html_content');
    if (htmlEl) {
      htmlEl.addEventListener('input', schedulePreviewRefresh);
    }

    var textEl = $('id_text_content');
    if (textEl) {
      textEl.addEventListener('input', schedulePreviewRefresh);
    }

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
