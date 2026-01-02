(function (window, document) {
  'use strict';

  function $(id) {
    return document.getElementById(id);
  }

  function getCsrfToken() {
    var el = document.querySelector('input[name=csrfmiddlewaretoken]');
    return el ? String(el.value || '') : '';
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

  var previewTimer = null;

  function schedulePreviewRefresh() {
    if (previewTimer) window.clearTimeout(previewTimer);
    previewTimer = window.setTimeout(refreshPreview, 200);
  }

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

  function enable(el, on) {
    if (!el) return;
    el.disabled = !on;
  }

  function storeOriginalsFromFields() {
    var form = $('election-edit-form');
    if (!form) return;

    form.dataset.originalSubject = getField('id_subject');
    form.dataset.originalHtml = getField('id_html_content');
    form.dataset.originalText = getField('id_text_content');

    enable($('mailmerge-restore-btn'), true);
  }

  function restoreOriginals() {
    var form = $('election-edit-form');
    if (!form) return;
    setField('id_subject', form.dataset.originalSubject || '');
    setField('id_html_content', form.dataset.originalHtml || '');
    setField('id_text_content', form.dataset.originalText || '');
    schedulePreviewRefresh();
  }

  function electionIdFromPath() {
    var parts = String(window.location.pathname || '').split('/').filter(Boolean);
    // /elections/<id>/edit/
    if (parts.length >= 3 && parts[0] === 'elections' && parts[2] === 'edit') {
      var n = parseInt(parts[1], 10);
      return isFinite(n) ? n : null;
    }

    // /elections/0/edit/
    if (parts.length >= 2 && parts[0] === 'elections' && parts[1] === 'new') {
      return 0;
    }
    return null;
  }

  function eligibleUsersSearchUrlFromPath() {
    var electionId = electionIdFromPath();
    if (electionId == null) return null;
    return '/elections/' + encodeURIComponent(String(electionId)) + '/eligible-users/search/';
  }

  function collectSelectedCandidates() {
    var $ = window.jQuery;
    if (!$) return [];

    var out = [];
    var seen = {};

    $('select[name^="candidates-"][name$="-freeipa_username"]').each(function () {
      var $sel = $(this);
      var name = String($sel.attr('name') || '');
      var m = name.match(/^candidates-(\d+)-freeipa_username$/);
      if (!m) return;

      var idx = m[1];
      var del = $('input[name="candidates-' + idx + '-DELETE"]');
      if (del.length && del.prop('checked')) return;

      var v = $sel.val();
      if (!v) return;
      var u = String(v).trim();
      if (!u) return;
      if (seen[u]) return;
      seen[u] = true;

      var label = String($sel.find('option:selected').text() || '').trim();
      if (!label) label = u;
      out.push({ id: u, text: label });
    });

    out.sort(function (a, b) {
      return a.id.toLowerCase().localeCompare(b.id.toLowerCase());
    });
    return out;
  }

  function syncGroupCandidateOptions(root) {
    var $ = window.jQuery;
    if (!$) return;

    var elRoot = root || document;
    var candidates = collectSelectedCandidates();

    $(elRoot).find('select[name^="groups-"][name$="-candidate_usernames"]').each(function () {
      var $sel = $(this);
      var selected = $sel.val();
      if (!Array.isArray(selected)) selected = selected ? [selected] : [];

      var allowed = {};
      for (var i = 0; i < candidates.length; i++) {
        allowed[candidates[i].id] = candidates[i].text;
      }

      // Remove options that are no longer candidates.
      $sel.find('option').each(function () {
        var v = String(this.value || '').trim();
        if (!v) return;
        if (!Object.prototype.hasOwnProperty.call(allowed, v)) {
          this.remove();
        }
      });

      // Add options for all current candidates.
      for (var j = 0; j < candidates.length; j++) {
        var u = candidates[j].id;
        var text = candidates[j].text;
        if ($sel.find('option[value="' + u.replace(/"/g, '\\"') + '"]').length) continue;
        var opt = new window.Option(text, u, false, false);
        $sel.append(opt);
      }

      // Drop selections that no longer exist.
      var nextSelected = [];
      for (var k = 0; k < selected.length; k++) {
        var sv = String(selected[k] || '').trim();
        if (Object.prototype.hasOwnProperty.call(allowed, sv)) nextSelected.push(sv);
      }
      $sel.val(nextSelected);

      $sel.trigger('change');
    });
  }

  async function refreshPreview() {
    var electionId = electionIdFromPath();
    if (!electionId) return;

    var data = new window.FormData();
    data.append('subject', getField('id_subject'));
    data.append('html_content', getField('id_html_content'));
    data.append('text_content', getField('id_text_content'));

    try {
      var resp = await window.fetch('/elections/' + encodeURIComponent(String(electionId)) + '/email/render-preview/', {
        method: 'POST',
        headers: { 'X-CSRFToken': getCsrfToken(), 'Accept': 'application/json' },
        body: data
      });
      var payload = await resp.json();
      if (!resp.ok) {
        if (payload && payload.error) {
          setPreviewText(payload.error);
        }
        return;
      }
      setPreviewHtml(payload.html);
      setPreviewText(payload.text);
    } catch (_e) {
      // Ignore transient failures.
    }
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
      storeOriginalsFromFields();
      schedulePreviewRefresh();
    } catch (_e) {
      try { window.alert('Failed to load template.'); } catch (__e) { /* noop */ }
    }
  }

  async function saveTemplate(templateId) {
    if (!templateId) {
      try { window.alert('Select a template to save, or use Save as.'); } catch (_e) { /* noop */ }
      return;
    }

    var data = new window.FormData();
    data.append('email_template_id', String(templateId));
    data.append('subject', getField('id_subject'));
    data.append('html_content', getField('id_html_content'));
    data.append('text_content', getField('id_text_content'));

    try {
      var resp = await window.fetch(
        '/email-tools/templates/save/',
        {
          method: 'POST',
          headers: { 'X-CSRFToken': getCsrfToken(), 'Accept': 'application/json' },
          body: data
        }
      );
      var payload = await resp.json();
      if (!resp.ok || !payload || payload.ok !== true) {
        throw new Error(payload && payload.error ? payload.error : 'save failed');
      }
      storeOriginalsFromFields();
      try { window.alert('Template saved.'); } catch (_e) { /* noop */ }
    } catch (_e) {
      try { window.alert('Failed to save template.'); } catch (__e) { /* noop */ }
    }
  }

  async function saveAsTemplate(name) {
    if (!name) return null;

    var data = new window.FormData();
    data.append('name', String(name));
    data.append('subject', getField('id_subject'));
    data.append('html_content', getField('id_html_content'));
    data.append('text_content', getField('id_text_content'));

    try {
      var resp = await window.fetch(
        '/email-tools/templates/save-as/',
        {
          method: 'POST',
          headers: { 'X-CSRFToken': getCsrfToken(), 'Accept': 'application/json' },
          body: data
        }
      );
      var payload = await resp.json();
      if (!resp.ok || !payload || payload.ok !== true) {
        throw new Error(payload && payload.error ? payload.error : 'save as failed');
      }
      return payload;
    } catch (_e) {
      return null;
    }
  }

  function initSelect2(root) {
    var $ = window.jQuery;
    if (!$ || !$.fn || !$.fn.select2) return;

    var elRoot = root || document;
    $(elRoot).find('select.alx-select2').each(function () {
      var $select = $(this);
      if ($select.data('alx-select2-initialized')) return;
      $select.data('alx-select2-initialized', true);

      var ajaxUrl = $select.attr('data-ajax-url') || $select.data('ajax-url');
      var startSourceId = $select.attr('data-start-datetime-source') || $select.data('start-datetime-source');

      var name = String($select.attr('name') || '');
      var id = String($select.attr('id') || '');
      var looksLikeEligibleUserSelect = Boolean(
        startSourceId ||
        /-freeipa_username$/.test(name) ||
        /-nominated_by$/.test(name) ||
        /-freeipa_username$/.test(id) ||
        /-nominated_by$/.test(id)
      );

      var looksLikeCandidateGroupSelect = Boolean(
        /-candidate_usernames$/.test(name) ||
        /-candidate_usernames$/.test(id)
      );

      // Exclusion-group candidate selection is handled as a plain <select multiple>.
      // Do not initialize Select2 for that field.
      if (looksLikeCandidateGroupSelect) {
        return;
      }

      if (!startSourceId && looksLikeEligibleUserSelect && document.getElementById('id_start_datetime')) {
        startSourceId = 'id_start_datetime';
      }

      // Newly-added formset rows can lose data-* attrs after template cloning/reparse.
      // Infer which selects should use the eligible-user search based on their field name.
      if (!ajaxUrl && looksLikeEligibleUserSelect) {
        ajaxUrl = eligibleUsersSearchUrlFromPath();
      }

      if (ajaxUrl) {
        $select.select2({
          width: '100%',
          allowClear: true,
          minimumInputLength: 0,
          closeOnSelect: !$select.prop('multiple'),
          ajax: {
            url: ajaxUrl,
            dataType: 'json',
            delay: 200,
            data: function (params) {
              var payload = {
                q: params && params.term != null ? String(params.term) : ''
              };
              if (startSourceId) {
                var startEl = document.getElementById(String(startSourceId));
                if (startEl && startEl.value) payload.start_datetime = String(startEl.value);
              }
              return payload;
            }
          }
        });

      } else {
        $select.select2({ width: '100%', closeOnSelect: !$select.prop('multiple') });
      }
    });
  }

  function addFormsetRow(prefix, emptyTemplateId, tbodyId) {
    var totalEl = $('id_' + prefix + '-TOTAL_FORMS');
    var tmpl = $(emptyTemplateId);
    var tbody = $(tbodyId);
    if (!totalEl || !tmpl || !tbody) return;

    var total = parseInt(String(totalEl.value || '0'), 10);
    if (!isFinite(total)) total = 0;

    var html = String(tmpl.innerHTML || '').replace(/__prefix__/g, String(total));

    var tmp = document.createElement('tbody');
    tmp.innerHTML = html;
    while (tmp.firstElementChild) {
      tbody.appendChild(tmp.firstElementChild);
    }

    totalEl.value = String(total + 1);
    initSelect2(tbody);
    syncGroupCandidateOptions(document);
  }

  function markRowDeleted(row) {
    if (!row) return;
    var del = row.querySelector('input[name$="-DELETE"]');
    if (del) {
      // Django formset DELETE fields are typically checkboxes, but treat them generically.
      del.checked = true;
      del.value = 'on';
      try {
        del.dispatchEvent(new window.Event('change', { bubbles: true }));
      } catch (_e) {
        // IE11-era fallback not needed; ignore.
      }
    }
    row.style.display = 'none';
  }

  function onReady() {
    function resetEmailSaveMode() {
      var mode = $('election-edit-email-save-mode');
      if (mode) mode.value = '';
    }

    var templateSelect = $('id_email_template_id');
    if (templateSelect) {
      templateSelect.addEventListener('change', function () {
        resetEmailSaveMode();
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
        var id = templateSelect ? String(templateSelect.value || '').trim() : '';
        if (!id) {
          saveTemplate(id);
          return;
        }

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
        if (ok) saveTemplate(id);
      });
    }

    var saveAsBtn = $('mailmerge-save-as-btn');
    if (saveAsBtn) {
      saveAsBtn.addEventListener('click', async function (e) {
        e.preventDefault();
        var jq = window.jQuery;
        if (jq && jq.fn && typeof jq.fn.modal === 'function') {
          var nameEl = document.getElementById('templated-email-save-as-name');
          if (nameEl) nameEl.value = '';
          jq('#templated-email-save-as-modal').modal('show');
          // Focus after the modal opens.
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

        var payload = await saveAsTemplate(name);
        if (!payload) {
          try { window.alert('Failed to create template.'); } catch (_e) { /* noop */ }
          return;
        }

        if (templateSelect && payload.id != null) {
          var opt = new window.Option(String(payload.name || name), String(payload.id), true, true);
          templateSelect.appendChild(opt);
          templateSelect.value = String(payload.id);
        }

        // If the user explicitly created a new template, they almost certainly
        // intend to save it onto the election draft too.
        var saveModeEl = $('election-edit-email-save-mode');
        if (saveModeEl) saveModeEl.value = 'save';

        storeOriginalsFromFields();
        schedulePreviewRefresh();
        try { window.alert('Template created.'); } catch (_e) { /* noop */ }
      });
    }

    // Wire modal confirm forms (shared by election edit + mailmerge).
    var saveModal = $('templated-email-save-modal');
    if (saveModal) {
      var formEl = saveModal.querySelector('form');
      if (formEl) {
        formEl.addEventListener('submit', function (e) {
          e.preventDefault();
          var id = templateSelect ? String(templateSelect.value || '').trim() : '';
          var jq = window.jQuery;
          if (jq && jq.fn && typeof jq.fn.modal === 'function') jq('#templated-email-save-modal').modal('hide');
          saveTemplate(id);
        });
      }
    }

    var saveAsModal = $('templated-email-save-as-modal');
    if (saveAsModal) {
      var formEl2 = saveAsModal.querySelector('form');
      if (formEl2) {
        formEl2.addEventListener('submit', async function (e) {
          e.preventDefault();
          var nameEl = $('templated-email-save-as-name');
          var name = nameEl ? String(nameEl.value || '').trim() : '';
          if (!name) return;

          var payload = await saveAsTemplate(name);
          if (!payload) {
            try { window.alert('Failed to create template.'); } catch (_e) { /* noop */ }
            return;
          }

          if (templateSelect && payload.id != null) {
            var opt = new window.Option(String(payload.name || name), String(payload.id), true, true);
            templateSelect.appendChild(opt);
            templateSelect.value = String(payload.id);
          }

          var saveModeEl = $('election-edit-email-save-mode');
          if (saveModeEl) saveModeEl.value = 'save';

          storeOriginalsFromFields();
          schedulePreviewRefresh();
          var jq = window.jQuery;
          if (jq && jq.fn && typeof jq.fn.modal === 'function') jq('#templated-email-save-as-modal').modal('hide');
          try { window.alert('Template created.'); } catch (_e) { /* noop */ }
        });
      }
    }

    var htmlEl = $('id_html_content');
    if (htmlEl) htmlEl.addEventListener('input', schedulePreviewRefresh);

    var textEl = $('id_text_content');
    if (textEl) textEl.addEventListener('input', schedulePreviewRefresh);

    var subjEl = $('id_subject');
    if (subjEl) subjEl.addEventListener('input', schedulePreviewRefresh);

    // Make restore meaningful even before the user loads a template.
    storeOriginalsFromFields();

    syncGroupCandidateOptions(document);
    initSelect2(document);

    var jq = window.jQuery;
    if (jq) {
      jq(document).on('change', 'select[name^="candidates-"][name$="-freeipa_username"], input[name^="candidates-"][name$="-DELETE"]', function () {
        syncGroupCandidateOptions(document);
      });
    }

    var addCandidateBtn = $('candidates-add-row');
    if (addCandidateBtn) {
      addCandidateBtn.addEventListener('click', function (e) {
        e.preventDefault();
        addFormsetRow('candidates', 'candidates-empty-form', 'candidates-formset-body');
      });
    }

    var addGroupBtn = $('groups-add-row');
    if (addGroupBtn) {
      addGroupBtn.addEventListener('click', function (e) {
        e.preventDefault();
        addFormsetRow('groups', 'groups-empty-form', 'groups-formset-body');
      });
    }

    // Prefer jQuery delegation because it already exists on this page and is
    // robust across dynamic formset rows.
    if (jq) {
      jq(document).on('click', '.election-edit-remove-row', function (e) {
        e.preventDefault();
        var row = null;
        if (this && this.closest) {
          row = this.closest('tr');
        }
        if (!row) {
          row = jq(this).closest('tr')[0] || null;
        }
        markRowDeleted(row);
      });
    } else {
      document.addEventListener('click', function (e) {
        var t = e.target;
        if (!t) return;
        var btn = null;
        if (t.classList && t.classList.contains('election-edit-remove-row')) {
          btn = t;
        } else if (t.closest) {
          btn = t.closest('.election-edit-remove-row');
        }
        if (!btn) return;

        e.preventDefault();
        var row = btn.closest ? btn.closest('tr') : null;
        markRowDeleted(row);
      });
    }

    var form = $('election-edit-form');
    if (form) {
      form.addEventListener('submit', function (e) {
        var actionEl = $('election-edit-action');
        var action = actionEl ? String(actionEl.value || '') : '';
        if (action !== 'save_draft') return;

        var hasElection = String(($('election-edit-has-election') || {}).value || '') === '1';
        var status = String(($('election-edit-election-status') || {}).value || '');
        if (!hasElection || status !== 'draft') return;

        var origId = String(($('election-edit-original-email-template-id') || {}).value || '').trim();
        var currentId = templateSelect ? String(templateSelect.value || '').trim() : '';
        var saveModeEl = $('election-edit-email-save-mode');
        var saveMode = saveModeEl ? String(saveModeEl.value || '').trim() : '';

        if (origId !== currentId && !saveMode) {
          e.preventDefault();

          var jq = window.jQuery;
          if (jq && jq.fn && typeof jq.fn.modal === 'function') {
            jq('#edit-template-changed-modal').modal('show');
            return;
          }

          // Fallback if Bootstrap modal isn't available.
          var ok = false;
          try {
            ok = window.confirm('Email template changed. OK to save new template + contents?\nCancel to keep previously saved email.');
          } catch (_e) {
            ok = false;
          }
          if (saveModeEl) saveModeEl.value = ok ? 'save' : 'keep_existing';
          form.submit();
        }
      });
    }

    var keepBtn = $('edit-keep-existing-email-btn');
    if (keepBtn) {
      keepBtn.addEventListener('click', function (e) {
        e.preventDefault();
        var saveModeEl = $('election-edit-email-save-mode');
        if (saveModeEl) saveModeEl.value = 'keep_existing';
        var jq = window.jQuery;
        if (jq && jq.fn && typeof jq.fn.modal === 'function') jq('#edit-template-changed-modal').modal('hide');
        if (form) form.submit();
      });
    }

    var saveBtn = $('edit-save-email-btn');
    if (saveBtn) {
      saveBtn.addEventListener('click', function (e) {
        e.preventDefault();
        var saveModeEl = $('election-edit-email-save-mode');
        if (saveModeEl) saveModeEl.value = 'save';
        var jq = window.jQuery;
        if (jq && jq.fn && typeof jq.fn.modal === 'function') jq('#edit-template-changed-modal').modal('hide');
        if (form) form.submit();
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', onReady);
  } else {
    onReady();
  }
})(window, document);
