(function () {
  'use strict';

  var REFRESH_MS = 5000;
  var DASH = '—';
  var inFlight = false;

  function el(tag, text, cls) {
    var node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  }

  function isNull(v) {
    return v === null || v === undefined || v === '';
  }

  // A cell whose value may be null (the event has not arrived yet): show a dash.
  function cell(value, cls) {
    var td = el('td');
    if (cls) td.className = cls;
    if (isNull(value)) {
      td.appendChild(el('span', DASH, 'dash'));
      td.title = 'not received yet';
    } else {
      td.textContent = String(value);
    }
    return td;
  }

  function statusCell(status) {
    var td = el('td');
    if (isNull(status)) {
      td.appendChild(el('span', DASH, 'dash'));
    } else {
      var s = String(status);
      td.appendChild(el('span', s, 'status status-' + s.replace(/[^a-z]/g, '')));
    }
    return td;
  }

  function stepsCell(steps) {
    var td = el('td');
    if (!Array.isArray(steps) || steps.length === 0) {
      td.appendChild(el('span', DASH, 'dash'));
      return td;
    }
    var ul = el('ul', undefined, 'steps');
    steps.forEach(function (step) {
      ul.appendChild(el('li', String(step.name) + ': ' + String(step.status)));
    });
    td.appendChild(ul);
    return td;
  }

  function failureText(b) {
    if (!isNull(b.failed_step)) return 'step "' + b.failed_step + '" failed';
    if (!isNull(b.failure_reason)) return b.failure_reason;
    return null;
  }

  function buildRow(b) {
    var tr = el('tr');
    tr.appendChild(cell(b.pipeline_name));
    tr.appendChild(cell(b.build_id, 'mono'));
    tr.appendChild(statusCell(b.status));
    tr.appendChild(cell(b.started_at, 'time'));
    tr.appendChild(cell(b.finished_at, 'time'));
    tr.appendChild(stepsCell(b.steps));
    tr.appendChild(cell(failureText(b)));
    return tr;
  }

  function artifactRow(a) {
    var tr = el('tr');
    tr.appendChild(cell(a.name));
    tr.appendChild(cell(a.version, 'num'));
    tr.appendChild(cell(a.checksum, 'mono'));
    tr.appendChild(cell(isNull(a.size_bytes) ? null : a.size_bytes + ' bytes', 'num'));
    tr.appendChild(cell(a.build_id, 'mono'));
    tr.appendChild(cell(a.uploaded_at, 'time'));
    return tr;
  }

  function releaseRow(r) {
    var tr = el('tr');
    var art = r.artifact;
    tr.appendChild(cell(art ? String(art.name) + ' v' + String(art.version) : null));
    tr.appendChild(statusCell(r.status));
    tr.appendChild(cell(r.requested_by));
    tr.appendChild(cell(r.requested_at, 'time'));
    tr.appendChild(cell(r.decided_by));
    tr.appendChild(cell(r.decided_at, 'time'));
    return tr;
  }

  var views = [
    { id: 'builds', url: '/builds?limit=200', row: buildRow, empty: 'No builds yet.' },
    { id: 'failures', url: '/builds?status=failed&limit=200', row: buildRow, empty: 'No failed builds.' },
    { id: 'artifacts', url: '/artifacts?limit=200', row: artifactRow, empty: 'No artifacts yet.' },
    { id: 'releases', url: '/releases?limit=200', row: releaseRow, empty: 'No releases yet.' }
  ];

  function show(view, items) {
    var state = document.getElementById(view.id + '-state');
    var wrap = document.getElementById(view.id + '-wrap');
    var body = document.getElementById(view.id + '-body');
    var rows = items.map(view.row);
    body.replaceChildren.apply(body, rows);
    state.className = 'state';
    if (rows.length === 0) {
      state.textContent = view.empty;
      state.hidden = false;
      wrap.hidden = true;
    } else {
      state.textContent = '';
      state.hidden = true;
      wrap.hidden = false;
    }
  }

  function showError(view, message) {
    // Keep the last good rows visible; say that they may be out of date.
    var state = document.getElementById(view.id + '-state');
    state.className = 'state error';
    state.textContent = 'Could not load ' + view.id + ': ' + message + '. Retrying in 5 seconds.';
    state.hidden = false;
  }

  function load(view) {
    return fetch(view.url, { headers: { Accept: 'application/json' }, cache: 'no-store' })
      .then(function (res) {
        if (!res.ok) throw new Error('server answered ' + res.status);
        return res.json();
      })
      .then(function (page) {
        if (!page || !Array.isArray(page.items)) throw new Error('unexpected response');
        show(view, page.items);
        return true;
      })
      .catch(function (err) {
        showError(view, err && err.message ? err.message : 'request failed');
        return false;
      });
  }

  function refresh() {
    if (inFlight) return;
    inFlight = true;
    Promise.all(views.map(load)).then(function (results) {
      inFlight = false;
      var note = document.getElementById('last-updated');
      if (results.every(Boolean)) {
        note.textContent = 'Last updated ' + new Date().toLocaleTimeString() + '.';
      } else {
        note.textContent = 'Some data could not be refreshed.';
      }
    });
  }

  refresh();
  setInterval(refresh, REFRESH_MS);
})();
