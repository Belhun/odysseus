/** Finance Goals panel. Progress is computed on the server from posted books. */

export async function renderFinanceGoals(ctx) {
  const panel = ctx.panel;
  const api = ctx.api;
  const moneyHtml = ctx.moneyHtml;
  const esc = ctx.escHtml;
  if (typeof window !== 'undefined') window.renderFinanceGoals = renderFinanceGoals;

  async function load() {
    panel.innerHTML = '<p>Loading goals…</p>';
    try {
      const [data, accounts, cats] = await Promise.all([
        api('/goals'),
        api('/accounts'),
        api('/categories'),
      ]);
      const goals = data.goals || [];
      const acctOpts = (accounts.accounts || [])
        .map((a) => `<option value="${esc(a.id)}">${esc(a.name)}</option>`)
        .join('');
      const catOpts = (cats.categories || [])
        .map((c) => `<option value="${esc(c.id)}">${esc(c.display_name || c.name)}</option>`)
        .join('');
      const rows = goals.map((g) => {
        const pct = Math.max(0, Math.min(100, g.percent || 0));
        const sug = g.suggested_monthly_cents
          ? ` · ${moneyHtml(g.suggested_monthly_cents)} / mo`
          : '';
        return `<div class="finance-card" style="margin-bottom:10px;border:1px solid var(--border,#355A66);border-radius:8px;padding:12px;">
          <div style="display:flex;justify-content:space-between;gap:8px;">
            <strong>${esc(g.name)}</strong>
            <span>${esc(g.kind)} · ${esc(g.target_date || 'no date')}</span>
          </div>
          <div class="finance-money">${moneyHtml(g.current_cents)} / ${moneyHtml(g.target_cents)}</div>
          <div style="height:8px;background:var(--border,#355A66);border-radius:4px;margin:8px 0;">
            <div style="height:8px;width:${pct}%;background:${esc(g.color || '#5b8abf')};border-radius:4px;"></div>
          </div>
          <p style="font-size:0.85rem;margin:0;">${pct}% · remaining ${moneyHtml(g.remaining_cents)}${sug}</p>
          <p style="margin:8px 0 0;display:flex;gap:8px;">
            <button type="button" class="btn-secondary" data-goal-edit="${esc(g.id)}">Edit</button>
            <button type="button" class="btn-secondary" data-goal-del="${esc(g.id)}">Delete</button>
          </p>
        </div>`;
      }).join('') || '<p>No goals yet. Add a savings or loan target. Progress uses posted balances, not envelopes.</p>';

      panel.innerHTML = `
        <h3 style="margin-top:0;">Goals</h3>
        <p style="font-size:0.85rem;opacity:0.85;">Progress is posted of a linked account (or true-spend of a category). Odysseus does not move envelope dollars.</p>
        ${rows}
        <form id="finance-goal-form" style="margin-top:16px;display:grid;gap:8px;max-width:420px;">
          <input type="hidden" name="goal_id" value="">
          <input name="name" placeholder="Emergency fund" required>
          <select name="kind">
            <option value="account">Account-linked</option>
            <option value="loan">Loan payoff</option>
            <option value="category">Category</option>
          </select>
          <input name="target_dollars" type="number" step="0.01" placeholder="Target dollars" required>
          <input name="baseline_dollars" type="number" step="0.01" placeholder="Baseline dollars (optional)">
          <input name="target_date" type="date">
          <select name="account_id"><option value="">Account (optional)</option>${acctOpts}</select>
          <select name="category_id"><option value="">Category (optional)</option>${catOpts}</select>
          <button type="submit" class="btn-primary" id="finance-goal-save">Add goal</button>
          <button type="button" class="btn-secondary" id="finance-goal-reset">Clear form</button>
          <div id="finance-goal-err" style="color:var(--danger,#e06c75);"></div>
        </form>`;

      const form = panel.querySelector('#finance-goal-form');
      const saveBtn = panel.querySelector('#finance-goal-save');
      panel.querySelector('#finance-goal-reset')?.addEventListener('click', () => {
        form?.reset();
        if (form) form.goal_id.value = '';
        if (saveBtn) saveBtn.textContent = 'Add goal';
      });
      panel.querySelectorAll('[data-goal-del]').forEach((btn) => {
        btn.addEventListener('click', async () => {
          await api(`/goals/${btn.dataset.goalDel}`, { method: 'DELETE' });
          await load();
        });
      });
      panel.querySelectorAll('[data-goal-edit]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const g = goals.find((row) => row.id === btn.dataset.goalEdit);
          if (!g || !form) return;
          form.goal_id.value = g.id;
          form.name.value = g.name;
          form.kind.value = g.kind;
          form.target_dollars.value = (g.target_cents / 100).toFixed(2);
          form.baseline_dollars.value = g.baseline_cents ? (g.baseline_cents / 100).toFixed(2) : '';
          form.target_date.value = g.target_date || '';
          form.account_id.value = g.account_id || '';
          form.category_id.value = g.category_id || '';
          if (saveBtn) saveBtn.textContent = 'Save goal';
        });
      });
      form?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const err = panel.querySelector('#finance-goal-err');
        const dollars = parseFloat(form.target_dollars.value || '0');
        const baseline = parseFloat(form.baseline_dollars.value || '0');
        const payload = {
          name: form.name.value,
          kind: form.kind.value,
          target_cents: Math.round(dollars * 100),
          baseline_cents: Math.round(baseline * 100),
          target_date: form.target_date.value || null,
          account_id: form.account_id.value || null,
          category_id: form.category_id.value || null,
        };
        try {
          const id = form.goal_id.value;
          if (id) {
            await api(`/goals/${id}`, {
              method: 'PATCH',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(payload),
            });
          } else {
            await api('/goals', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(payload),
            });
          }
          await load();
        } catch (ex) {
          if (err) err.textContent = ex.message || String(ex);
        }
      });
    } catch (e) {
      panel.innerHTML = `<p>Could not load goals: ${esc(e.message || e)}</p>
        <button type="button" class="btn-secondary" id="finance-goal-retry">Retry</button>`;
      panel.querySelector('#finance-goal-retry')?.addEventListener('click', load);
    }
  }

  await load();
}

if (typeof window !== 'undefined') {
  window.renderFinanceGoals = renderFinanceGoals;
  window.renderFinanceGoals = renderFinanceGoals;
}
