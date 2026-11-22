-- Wents Workshop · security
-- Rule: only a signed-in user whose email is in public.staff (active) can read
-- or write anything.  The anon key alone gets nothing; a stray sign-up (if
-- sign-ups were ever re-enabled) gets nothing either until the email is added
-- to staff.  Service role (import script, dashboard) bypasses RLS as usual.

create or replace function public.is_staff() returns boolean
language sql stable security definer
set search_path = public
as $$
  select coalesce(auth.role(), '') = 'authenticated'
     and exists (
       select 1 from public.staff s
       where s.active
         and lower(s.email) = lower(coalesce(auth.jwt() ->> 'email', ''))
     );
$$;
revoke all on function public.is_staff() from public, anon;
grant execute on function public.is_staff() to authenticated;

-- Nothing for anon or public on any table, sequence or function in this schema.
revoke all on all tables in schema public from anon, public;
revoke all on all sequences in schema public from anon, public;
revoke all on all functions in schema public from anon, public;
alter default privileges in schema public revoke all on tables from anon, public;
alter default privileges in schema public revoke all on sequences from anon, public;
alter default privileges in schema public revoke all on functions from anon, public;

-- Authenticated users may touch the tables, but RLS below lets only staff through.
grant select, insert, update, delete on
  public.customers, public.vehicles, public.invoices, public.invoice_lines, public.payments,
  public.quotes, public.jobsheets, public.bookings, public.day_notes, public.settings
  to authenticated;
grant select on public.staff to authenticated;
-- Payments, quotes and jobsheets get their numbers from a default nextval, so
-- inserting needs usage.  Invoice numbers are assigned only inside
-- ws_create_invoice (0003), so invoice_no_seq is NOT granted.
grant usage on sequence public.payment_id_seq, public.quote_no_seq, public.jobsheet_no_seq, public.invoice_lines_id_seq to authenticated;

do $$
declare t text;
begin
  foreach t in array array['staff','customers','vehicles','invoices','invoice_lines','payments','quotes','jobsheets','bookings','day_notes','settings'] loop
    execute format('alter table public.%I enable row level security', t);
  end loop;
  -- staff: read-only for staff (so the app can show the signed-in name); edits only in the dashboard
  execute 'create policy staff_read on public.staff for select to authenticated using (public.is_staff())';
  foreach t in array array['customers','vehicles','invoices','invoice_lines','payments','quotes','jobsheets','bookings','day_notes','settings'] loop
    execute format('create policy %I_staff_all on public.%I for all to authenticated using (public.is_staff()) with check (public.is_staff())', t, t);
  end loop;
end $$;
