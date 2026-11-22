-- Wents Workshop · API functions the app calls over PostgREST /rpc
-- All of them refuse unless is_staff().  ws_snapshot returns the exact shapes
-- mock/index.html holds in memory (the same ones tools/garagebase/adapt.py
-- builds), so the pages need no changes.

-- Helpers for the app's display ids
create or replace function public.ws_inv_id(n integer) returns text language sql immutable as $$ select 'INV-' || lpad(n::text, 5, '0') $$;
create or replace function public.ws_q_id(n integer)   returns text language sql immutable as $$ select 'Q-'   || lpad(n::text, 4, '0') $$;
create or replace function public.ws_js_id(n integer)  returns text language sql immutable as $$ select 'JS-'  || n::text $$;
create or replace function public.ws_c_id(n integer)   returns text language sql immutable as $$ select case when n is null then '' else 'c' || n::text end $$;

-- One invoice in the app's shape
create or replace function public.ws_invoice_json(i public.invoices, p_jobs_exist boolean default true) returns jsonb
language sql stable
set search_path = public
as $$
  select jsonb_strip_nulls(jsonb_build_object(
    'n', ws_inv_id(i.no), 'cust', ws_c_id(i.cust), 'reg', coalesce(i.reg, ''), 'date', i.date, 'due', coalesce(i.due, i.date),
    'title', coalesce(i.title, ''), 'status', i.status, 'total', i.total, 'paid', i.paid, 'miles', coalesce(i.miles, 0),
    'adv', i.advise, 'note', coalesce(i.memo, ''),
    'lines', coalesce((select jsonb_agg(jsonb_build_object('k', l.kind, 'd', l.descr, 'q', l.qty, 'p', l.price) order by l.pos, l.id)
                       from invoice_lines l where l.invoice_no = i.no), '[]'::jsonb),
    'pays', coalesce((select jsonb_agg(jsonb_strip_nulls(jsonb_build_object('d', p.date, 'm', p.method, 'a', p.amount, 'ref', p.ref, 'who', p.who, 'seen', p.seen, 'pid', p.id)) order by p.date, p.id)
                      from payments p where p.invoice_no = i.no), '[]'::jsonb),
    'js', case when i.job is not null and exists (select 1 from jobsheets j where j.no = i.job) then ws_js_id(i.job) end,
    'hold', nullif(i.hold, ''),
    'cash', case when i.cash and coalesce(i.reg, '') = '' then true end,
    'mech', nullif(i.mechanic, '')
  )) || coalesce(i.app, '{}'::jsonb);
$$;

-- The whole working set.  p_years: invoices newer than this many years come
-- back in full; older ones as compact per-vehicle history (legacy).  Invoices
-- still owed, on hold or draft always come back in full.  p_since: only rows
-- changed after that time (delta sync); null = everything.
create or replace function public.ws_snapshot(p_years integer default 2, p_since timestamptz default null) returns jsonb
language plpgsql stable security invoker
set search_path = public
as $$
declare
  cutoff date := (current_date - (p_years * interval '1 year'))::date;
  r jsonb := '{}'::jsonb;
  names jsonb;
begin
  if not is_staff() then raise exception 'not staff' using errcode = '42501'; end if;

  select coalesce(jsonb_object_agg(ref::text, name), '{}') into names from customers;

  r := r || jsonb_build_object('customers', coalesce((
    select jsonb_agg(jsonb_build_object('id', ws_c_id(c.ref), 'name', c.name, 'phone', coalesce(c.phone, c.mobile, ''), 'email', coalesce(c.email, ''),
                                        'addr', coalesce(c.addr, ''), 'since', coalesce(left(c.since::text, 4), '')) order by c.ref)
    from customers c where p_since is null or c.updated_at > p_since), '[]'));

  r := r || jsonb_build_object('CX', coalesce((
    select jsonb_object_agg(ws_c_id(c.ref), jsonb_build_object(
      'ref', c.ref, 'acct', coalesce(c.account, 'Private'), 'terms', coalesce(c.terms, 0), 'rate', coalesce(c.rate, 68), 'disc', coalesce(c.discount, 0),
      'tel', coalesce(c.home, ''), 'mob', coalesce(c.mobile, c.phone, ''),
      'inv', coalesce(c.inv_addr, case when c.account = 'Account' then c.name else '' end),
      'prefs', case when c.prefs = '{}' then '{"rem":1,"stmt":0,"mail":0}'::jsonb else c.prefs end,
      'via', 'Text', 'heard', coalesce(c.heard, ''), 'accRef', coalesce(c.acc_ref, ''), 'notes', c.notes, 'files', '[]'::jsonb,
      'also', c.folded, 'contact', coalesce(c.contact, '')) || c.app)
    from customers c where p_since is null or c.updated_at > p_since), '{}'));

  r := r || jsonb_build_object('vehicles', coalesce((
    select jsonb_agg(jsonb_build_object('reg', v.reg, 'make', coalesce(v.label, 'Unknown'), 'year', coalesce(v.year::text, ''), 'cust', ws_c_id(v.cust),
                                        'miles', coalesce(v.miles, 0), 'mot', coalesce(v.mot::text, ''), 'fuel', coalesce(v.fuel, ''), 'colour', coalesce(v.colour, '')) order by v.reg)
    from vehicles v where p_since is null or v.updated_at > p_since), '[]'));

  r := r || jsonb_build_object('VX', coalesce((
    select jsonb_object_agg(v.reg, jsonb_build_object(
      'vin', coalesce(nullif(v.vin, ''), '—'), 'eng', coalesce(nullif(v.engine, ''), '—'), 'tyre', coalesce(nullif(v.tyre, ''), '—'),
      'oil', '—', 'key', '', 'tax', '', 'nuts', '—', 'prev', '[]'::jsonb,
      'notes', v.notes || coalesce((select jsonb_agg('Previously on GB Pro ref ' || (p->>'cust') || ' (' || coalesce(names->>(p->>'cust'), '') || ')')
                                    from jsonb_array_elements(v.prev) p), '[]'::jsonb)) || v.app)
    from vehicles v where p_since is null or v.updated_at > p_since), '{}'));

  r := r || jsonb_build_object('invoices', coalesce((
    select jsonb_agg(ws_invoice_json(i) order by i.no desc)
    from invoices i
    where (i.date is null or i.date >= cutoff or i.status not in ('paid', 'void'))
      and (p_since is null or i.updated_at > p_since)), '[]'));

  if p_since is null then
    r := r || jsonb_build_object('legacy', coalesce((
      select jsonb_object_agg(reg, hist) from (
        select i.reg, jsonb_agg(jsonb_build_object('d', i.date, 't', coalesce(i.title, ''), 'a', i.total, 'm', coalesce(i.miles, 0), 'n', ws_inv_id(i.no)) order by i.date desc) hist
        from invoices i
        where i.reg is not null and i.reg <> '' and i.date is not null and i.date < cutoff and i.status in ('paid', 'void')
        group by i.reg) x), '{}'));
  end if;

  r := r || jsonb_build_object('QUOTES', coalesce((
    select jsonb_agg(jsonb_strip_nulls(jsonb_build_object(
      'id', ws_q_id(q.no), 'c', ws_c_id(q.cust), 'r', coalesce(q.reg, ''), 't', coalesce(q.title, ''), 'st', q.status,
      'd', coalesce(q.date, '2019-01-01'::date), 'valid', coalesce(q.valid, q.date, '2019-01-01'::date), 'note', q.note, 'inote', q.inote,
      'adv', q.advise, 'lines', q.lines, 'opts', q.opts, 'hist', q.hist,
      'inv', case when q.became_invoice is not null then ws_inv_id(q.became_invoice) end)) || q.app order by q.no desc)
    from quotes q where p_since is null or q.updated_at > p_since), '[]'));

  r := r || jsonb_build_object('JOBS', coalesce((
    select jsonb_agg(jsonb_strip_nulls(jsonb_build_object(
      'id', ws_js_id(j.no), 't', coalesce(j.title, 'Job sheet'), 'c', ws_c_id(j.cust), 'r', coalesce(j.reg, ''), 'st', j.status,
      'a', coalesce(i.total, 0), 'who', '', 'miles', coalesce(i.miles, 0), 'keys', '', 'req', coalesce(j.description, ''),
      'found', trim(coalesce(j.work_done, '') || case when coalesce(j.problems, '') <> '' then ' Problems: ' || j.problems else '' end),
      'adv', j.advise, 'auth', '', 'lines', j.lines,
      'n', case when i.no is not null then ws_inv_id(i.no) end,
      'hold', nullif(j.hold, ''))) || j.app order by j.no desc)
    from jobsheets j left join invoices i on i.no = j.invoice
    where p_since is null or j.updated_at > p_since), '[]'));

  r := r || jsonb_build_object('REMS', coalesce((
    select jsonb_agg(jsonb_build_object('id', 'm' || replace(v.reg, ' ', ''), 'reg', v.reg, 'type', 'mot', 'due', v.mot, 'st', 'new', 'log', '[]'::jsonb) order by v.mot)
    from vehicles v where v.mot is not null and (p_since is null or v.updated_at > p_since)), '[]'));

  r := r || jsonb_build_object('BK', coalesce((
    select jsonb_object_agg(day::text, items) from (
      select b.day, jsonb_agg(b.data || jsonb_build_object('id', b.id) order by b.data->>'t', b.id) items
      from bookings b
      where not b.deleted and b.day >= current_date - 120 and (p_since is null or b.updated_at > p_since)
      group by b.day) x), '{}'));
  r := r || jsonb_build_object('BKdeleted', coalesce((
    select jsonb_agg(b.id) from bookings b where b.deleted and p_since is not null and b.updated_at > p_since), '[]'));

  r := r || jsonb_build_object('NOTES', coalesce((
    select jsonb_object_agg(day::text, notes) from day_notes n
    where n.day >= current_date - 120 and (p_since is null or n.updated_at > p_since)), '{}'));

  r := r || jsonb_build_object('settings', coalesce((
    select jsonb_object_agg(key, value) from settings s where p_since is null or s.updated_at > p_since), '{}'));

  r := r || jsonb_build_object('meta', jsonb_build_object(
    'years', p_years, 'cutoff', cutoff, 'since', p_since, 'at', now(),
    'customers', (select count(*) from customers), 'vehicles', (select count(*) from vehicles),
    'invoicesAll', (select count(*) from invoices),
    'invoicesFull', (select count(*) from invoices i where i.date is null or i.date >= cutoff or i.status not in ('paid', 'void')),
    'invoicesLegacy', (select count(*) from invoices i where i.reg is not null and i.reg <> '' and i.date < cutoff and i.status in ('paid', 'void')),
    'quotes', (select count(*) from quotes), 'jobs', (select count(*) from jobsheets),
    'lastInvoice', (select ws_inv_id(max(no)) from invoices), 'nextInvoice', ws_inv_id((select last_value + case when is_called then 1 else 0 end from invoice_no_seq)::integer),
    'owedTotal', (select coalesce(round(sum(total - paid), 2), 0) from invoices where status = 'owed'),
    'motDue30', (select count(*) from vehicles where mot between current_date and current_date + 30),
    'staff', (select jsonb_agg(jsonb_build_object('email', email, 'name', name, 'initials', initials, 'who', who_key)) from staff where active)
  ));
  return r;
end $$;
revoke all on function public.ws_snapshot(integer, timestamptz) from public, anon;
grant execute on function public.ws_snapshot(integer, timestamptz) to authenticated;

-- Write an invoice from the app's record ({n,cust,reg,date,due,title,status,total,paid,miles,adv,lines,note,pays,js,hold,cash,mech}).
-- p_no null = new invoice: the number comes from invoice_no_seq (78894 onwards).  Returns the number.
-- Lines are replaced.  Payments: GarageBase rows are kept; app rows are matched
-- on (date, method, amount, ref); unmatched app rows are deleted, new ones added.
create or replace function public.ws_save_invoice(p jsonb, p_no integer default null) returns integer
language plpgsql security invoker
set search_path = public
as $$
declare
  n integer := p_no;
  cust_ref integer := nullif(regexp_replace(coalesce(p->>'cust', ''), '^c', ''), '')::integer;
  job_no integer := nullif(regexp_replace(coalesce(p->>'js', ''), '^JS-', ''), '')::integer;
  l jsonb; i integer := 0;
  pay jsonb;
  tot numeric(12,2) := coalesce((p->>'total')::numeric, 0);
  pd numeric(12,2);
  extras jsonb := p - array['n','cust','reg','date','due','title','status','total','paid','miles','adv','lines','note','pays','js','hold','cash','mech'];
begin
  if not is_staff() then raise exception 'not staff' using errcode = '42501'; end if;
  if n is null then
    n := nextval('invoice_no_seq');
  end if;
  insert into invoices as inv (no, cust, reg, cash, date, due, title, advise, memo, job, status, hold, total, paid, mechanic, miles, app, source)
  values (n, cust_ref, nullif(p->>'reg', ''), coalesce((p->>'cash')::boolean, false), (p->>'date')::date, (p->>'due')::date,
          p->>'title', coalesce(p->'adv', '[]'), p->>'note', job_no, coalesce(p->>'status', 'draft'), p->>'hold',
          tot, coalesce((p->>'paid')::numeric, 0), p->>'mech', (p->>'miles')::integer, extras, 'app')
  on conflict (no) do update set
    cust = excluded.cust, reg = excluded.reg, cash = excluded.cash, date = excluded.date, due = excluded.due, title = excluded.title,
    advise = excluded.advise, memo = excluded.memo, job = excluded.job, status = excluded.status, hold = excluded.hold,
    total = excluded.total, paid = excluded.paid, mechanic = excluded.mechanic, miles = excluded.miles, app = inv.app || excluded.app;

  delete from invoice_lines where invoice_no = n;
  for l in select * from jsonb_array_elements(coalesce(p->'lines', '[]')) loop
    i := i + 1;
    insert into invoice_lines (invoice_no, pos, kind, descr, qty, price, total, cost, part_no, supplier)
    values (n, i, case when l->>'k' in ('job','prt','lab','mot') then l->>'k' else 'prt' end, coalesce(l->>'d', ''),
            coalesce((l->>'q')::numeric, 0), coalesce((l->>'p')::numeric, 0), round(coalesce((l->>'q')::numeric, 0) * coalesce((l->>'p')::numeric, 0), 2),
            (l->>'cost')::numeric, l->>'pn', l->>'sup');
  end loop;

  -- payments made in the app
  create temp table if not exists _pays (d date, m text, a numeric(12,2), ref text, who text, seen boolean) on commit drop;
  delete from _pays;
  for pay in select * from jsonb_array_elements(coalesce(p->'pays', '[]')) loop
    insert into _pays values ((pay->>'d')::date, pay->>'m', coalesce((pay->>'a')::numeric, 0), pay->>'ref', pay->>'who', (pay->>'seen')::boolean);
  end loop;
  delete from payments x where x.invoice_no = n and x.source = 'app'
    and not exists (select 1 from _pays t where t.d is not distinct from x.date and t.m is not distinct from x.method and t.a = x.amount and coalesce(t.ref, '') = coalesce(x.ref, ''));
  insert into payments (invoice_no, cust, date, amount, method, ref, who, seen, source)
  select n, cust_ref, t.d, t.a, t.m, t.ref, t.who, t.seen, 'app' from _pays t
  where not exists (select 1 from payments x where x.invoice_no = n and x.date is not distinct from t.d and x.method is not distinct from t.m and x.amount = t.a and coalesce(x.ref, '') = coalesce(t.ref, ''));
  select coalesce(sum(amount), 0) into pd from payments where invoice_no = n;
  update invoices set paid = pd where no = n and paid <> pd;
  return n;
end $$;
revoke all on function public.ws_save_invoice(jsonb, integer) from public, anon;
grant execute on function public.ws_save_invoice(jsonb, integer) to authenticated;

-- Next quote / jobsheet number for a brand-new record (the app renames its draft on first save).
create or replace function public.ws_next_no(kind text) returns integer
language plpgsql security invoker
set search_path = public
as $$
begin
  if not is_staff() then raise exception 'not staff' using errcode = '42501'; end if;
  return case kind when 'quote' then nextval('quote_no_seq') when 'jobsheet' then nextval('jobsheet_no_seq') end;
end $$;
revoke all on function public.ws_next_no(text) from public, anon;
grant execute on function public.ws_next_no(text) to authenticated;

-- After an import: move every sequence past the highest number in its table.
-- invoice_no_seq never goes below 78894.  Service role / dashboard only.
create or replace function public.ws_reset_sequences() returns jsonb
language plpgsql security invoker
set search_path = public
as $$
declare r jsonb;
begin
  perform setval('invoice_no_seq', greatest(78894, coalesce((select max(no) from invoices), 0) + 1), false);
  perform setval('quote_no_seq', coalesce((select max(no) from quotes), 0) + 1, false);
  perform setval('jobsheet_no_seq', coalesce((select max(no) from jobsheets), 0) + 1, false);
  perform setval('payment_id_seq', coalesce((select max(id) from payments), 0) + 1, false);
  select jsonb_build_object('nextInvoice', (select last_value from invoice_no_seq), 'nextQuote', (select last_value from quote_no_seq),
                            'nextJobsheet', (select last_value from jobsheet_no_seq), 'nextPayment', (select last_value from payment_id_seq)) into r;
  return r;
end $$;
revoke all on function public.ws_reset_sequences() from public, anon, authenticated;

-- A signed-in user's own staff row (name/initials for the header)
create or replace function public.ws_me() returns jsonb
language sql stable security invoker
set search_path = public
as $$
  select coalesce((select jsonb_build_object('email', email, 'name', name, 'initials', initials, 'who', who_key)
                   from staff where active and lower(email) = lower(coalesce(auth.jwt() ->> 'email', ''))), 'null'::jsonb);
$$;
revoke all on function public.ws_me() from public, anon;
grant execute on function public.ws_me() to authenticated;

-- lock down the helper functions too (immutable id formatters are harmless, but keep the rule simple)
revoke all on function public.ws_inv_id(integer), public.ws_q_id(integer), public.ws_js_id(integer), public.ws_c_id(integer), public.ws_invoice_json(public.invoices, boolean) from public, anon;
grant execute on function public.ws_inv_id(integer), public.ws_q_id(integer), public.ws_js_id(integer), public.ws_c_id(integer), public.ws_invoice_json(public.invoices, boolean) to authenticated;
