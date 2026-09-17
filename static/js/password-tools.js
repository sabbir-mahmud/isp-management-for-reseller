/*
 * Password helpers shared by the login and change-password screens.
 *
 * Everything here is a convenience layered over plain inputs: with scripts
 * off, the forms still post, and the server still validates every rule.
 *
 *   [data-password-input]   gets a Show/Hide button and a Caps Lock warning
 *   [data-strength-source]  drives [data-strength] and [data-rule] items
 *   [data-match-source]     drives [data-match] against the strength source
 *   form[data-once]         disables its submit button after the first submit
 */
(function () {
  'use strict';

  // ---- Show / hide, and Caps Lock -----------------------------------------

  document.querySelectorAll('input[data-password-input]').forEach((input) => {
    const wrap = document.createElement('div');
    wrap.className = 'password-field';
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);

    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'password-toggle';
    toggle.textContent = 'Show';
    toggle.setAttribute('aria-label', 'Show password');
    toggle.setAttribute('aria-pressed', 'false');
    toggle.addEventListener('click', () => {
      const showing = input.type === 'text';
      input.type = showing ? 'password' : 'text';
      toggle.textContent = showing ? 'Show' : 'Hide';
      toggle.setAttribute('aria-label', showing ? 'Show password' : 'Hide password');
      toggle.setAttribute('aria-pressed', showing ? 'false' : 'true');
      input.focus();
    });
    wrap.appendChild(toggle);

    const caps = document.createElement('div');
    caps.className = 'caps-warning';
    caps.hidden = true;
    caps.setAttribute('role', 'status');
    caps.textContent = 'Caps Lock is on';
    wrap.insertAdjacentElement('afterend', caps);

    const checkCaps = (event) => {
      if (typeof event.getModifierState === 'function') {
        caps.hidden = !event.getModifierState('CapsLock');
      }
    };
    input.addEventListener('keydown', checkCaps);
    input.addEventListener('keyup', checkCaps);
    input.addEventListener('blur', () => { caps.hidden = true; });
  });

  // ---- Strength and rules ---------------------------------------------------

  const source = document.querySelector('input[data-strength-source]');
  if (source) {
    const meter = document.querySelector('[data-strength]');
    const personal = JSON.parse((document.getElementById('personal-words') || {}).textContent || '[]')
      .map((word) => word.toLowerCase());

    // A rough score, not a promise: length matters most, then variety, and a
    // password built around your own name is capped low whatever else it has.
    const score = (value) => {
      if (!value) { return 0; }
      let points = Math.min(value.length, 20) / 4;                   // up to 5
      points += [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/]
        .filter((re) => re.test(value)).length * 0.75;               // up to 3
      if (/^(.)\1+$/.test(value) || /^\d+$/.test(value)) { points = Math.min(points, 1); }
      if (value.length < 8) { points = Math.min(points, 1.5); }
      return Math.max(1, Math.min(4, Math.round(points / 2)));
    };
    const LABELS = ['', 'Weak', 'Fair', 'Good', 'Strong'];

    const rules = {
      length: (v) => v.length >= 8,
      not_numeric: (v) => v.length > 0 && !/^\d+$/.test(v),
      // Either way round, but not on the first couple of keystrokes: nearly
      // any single letter appears somewhere in a name.
      not_personal: (v) => {
        const lower = v.toLowerCase();
        return v.length > 0 && !personal.some(
          (word) => lower.includes(word) || (lower.length >= 3 && word.includes(lower)),
        );
      },
    };

    const update = () => {
      const value = source.value;
      // Built around your own name is weak, however long the rest is.
      const level = rules.not_personal(value) ? score(value) : Math.min(score(value), 1);
      if (meter) {
        meter.dataset.level = String(level);
        meter.querySelector('[data-strength-label]').textContent = value ? LABELS[level] : 'Start typing';
      }
      document.querySelectorAll('[data-rule]').forEach((item) => {
        const check = rules[item.dataset.rule];
        if (!check) { return; }  // checked by the server only
        const state = value ? (check(value) ? 'pass' : 'fail') : '';
        item.dataset.state = state;
      });
      matchUpdate();
    };

    const confirm = document.querySelector('input[data-match-source]');
    const match = document.querySelector('[data-match]');
    const matchUpdate = () => {
      if (!confirm || !match) { return; }
      if (!confirm.value) {
        match.dataset.state = '';
        match.textContent = '';
      } else if (confirm.value === source.value) {
        match.dataset.state = 'pass';
        match.textContent = 'Matches';
      } else {
        const partial = source.value.startsWith(confirm.value);
        match.dataset.state = partial ? '' : 'fail';
        match.textContent = partial ? 'Keep typing…' : 'Does not match';
      }
    };

    source.addEventListener('input', update);
    if (confirm) { confirm.addEventListener('input', matchUpdate); }
    update();
  }

  // ---- One submit -----------------------------------------------------------

  document.querySelectorAll('form[data-once]').forEach((form) => {
    form.addEventListener('submit', () => {
      const button = form.querySelector('button[type=submit]');
      if (!button) { return; }
      // After the event, so the button's own name/value is still posted.
      setTimeout(() => {
        button.disabled = true;
        button.dataset.busy = '';
        if (button.dataset.busyLabel) { button.textContent = button.dataset.busyLabel; }
      }, 0);
    });
  });
})();
