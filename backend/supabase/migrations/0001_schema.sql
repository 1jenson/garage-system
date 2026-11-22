-- Wents Workshop · schema
-- Tables hold the GarageBase history (imported once by backend/import) plus
-- everything the Workshop app writes.  Primary keys are the GarageBase numbers
-- so an import can be re-run safely (upserts), and invoice numbers carry on
-- from the last GarageBase invoice (78893) via invoice_no_seq.
-- Every table gets row-level security in 0002_security.sql; nothing here is
-- readable without a staff login.

create extension if not exists pgcrypto;

-- Staff allowed into the app.  Jenson adds rows in the dashboard (Table editor)
-- and creates the matching auth user under Authentication > Users.
create table public.staff (
  email      text primary key,
  name       text not null default '',
  initials   text not null default '',
  who_key    text,                          -- the app's WHO key (adam, jen, karen...) if any
  active     boolean not null default true,
  created_at timestamptz not null default now()
);

create table public.customers (
  ref        integer primary key,           -- GarageBase customer ref; the app shows it as 'c<ref>'
  name       text not null default '',
  surname    text,
  title      text,
  contact    text,
  addr       text,
  postcode   text,
  phone      text,
  mobile     text,
  home       text,
  work       text,
  phones     jsonb not null default '[]',
  email      text,
  since      date,
  account    text,                          -- 'Private' | 'Account' ...
  terms      integer,
  credit     numeric(12,2),
  rate       numeric(10,2),
  discount   numeric(10,2),
  prefs      jsonb not null default '{}',   -- {rem,stmt,mail}
  heard      text,
  acc_ref    text,
  inv_addr   text,
  notes      jsonb not null default '[]',   -- [{d,t}]
  folded     jsonb not null default '[]',   -- GB refs merged into this one
  app        jsonb not null default '{}',   -- fields the Workshop app edits (the mock's CX record)
  source     text not null default 'app',   -- 'gb' imported, 'app' created here
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index customers_name_idx on public.customers (lower(name));
create index customers_updated_idx on public.customers (updated_at);

create table public.vehicles (
  reg         text primary key,             -- registration as GarageBase stored it (with the space)
  cust        integer references public.customers(ref) on delete set null,
  make        text,
  model       text,
  engine_size text,
  label       text,                         -- "Make Model 1.6" as the app shows it
  year        integer,
  mot         date,
  vin         text,
  engine      text,
  colour      text,
  tyre        text,
  fuel        text,
  miles       integer,
  notes       jsonb not null default '[]',  -- [text]
  prev        jsonb not null default '[]',  -- [{cust}] previous owners
  app         jsonb not null default '{}',  -- the mock's VX record as edited in the app
  source      text not null default 'app',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index vehicles_cust_idx on public.vehicles (cust);
create index vehicles_mot_idx on public.vehicles (mot);
create index vehicles_updated_idx on public.vehicles (updated_at);

-- Invoice numbers continue from GarageBase: last imported is 78893.
create sequence public.invoice_no_seq start with 78894 minvalue 78894 no cycle;

create table public.invoices (
  no           integer primary key,
  cust         integer references public.customers(ref) on delete set null,
  reg          text,                        -- no FK: 43 GarageBase invoices name a reg with no vehicle record
  cash         boolean not null default false,
  date         date,
  due          date,
  title        text,
  work         text,
  advise       jsonb not null default '[]',
  memo         text,
  job          integer,                     -- jobsheet number
  status       text not null default 'draft',  -- draft | owed | paid | hold | void
  hold         text,
  labour       numeric(12,2),
  hours        numeric(10,2),
  rate         numeric(10,2),
  parts        numeric(12,2),
  mot_fee      numeric(10,2),
  mot_pass     boolean,
  outside      numeric(12,2),
  others       numeric(12,2),
  lubricants   numeric(12,2),
  recovery     numeric(12,2),
  net          numeric(12,2),
  vat          numeric(12,2),
  vat_rate     numeric(6,2),
  total        numeric(12,2) not null default 0,
  paid         numeric(12,2) not null default 0,
  mechanic     text,
  miles        integer,
  next_service date,
  app          jsonb not null default '{}', -- extra app-side fields (hold reason, audit...)
  source       text not null default 'app',
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create index invoices_cust_idx on public.invoices (cust);
create index invoices_reg_idx on public.invoices (reg);
create index invoices_date_idx on public.invoices (date);
create index invoices_status_idx on public.invoices (status) where status in ('owed','draft','hold');
create index invoices_updated_idx on public.invoices (updated_at);

create table public.invoice_lines (
  id         bigserial primary key,
  invoice_no integer not null references public.invoices(no) on delete cascade,
  pos        integer not null default 0,
  kind       text not null check (kind in ('job','prt','lab','mot')),
  descr      text not null default '',
  qty        numeric(12,3) not null default 0,
  price      numeric(12,2) not null default 0,
  total      numeric(12,2),
  cost       numeric(12,2),
  part_no    text,
  supplier   text,
  gb_id      text,                          -- GarageBase line id (or a fixed tag for derived lines) for idempotent imports
  unique (invoice_no, gb_id)
);
create index invoice_lines_inv_idx on public.invoice_lines (invoice_no, pos);

create sequence public.payment_id_seq start with 1 no cycle;
create table public.payments (
  id         bigint primary key default nextval('public.payment_id_seq'),
  invoice_no integer references public.invoices(no) on delete set null,
  cust       integer references public.customers(ref) on delete set null,
  date       date,
  amount     numeric(12,2) not null default 0,
  method     text,                          -- Card | Cash | BACS | Cheque | ...
  method_raw text,
  ref        text,
  who        text,                          -- staff who took it (app only)
  seen       boolean,
  source     text not null default 'app',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index payments_inv_idx on public.payments (invoice_no);
create index payments_date_idx on public.payments (date);
alter sequence public.payment_id_seq owned by public.payments.id;

create sequence public.quote_no_seq start with 1 no cycle;
create table public.quotes (
  no             integer primary key default nextval('public.quote_no_seq'),
  cust           integer references public.customers(ref) on delete set null,
  reg            text,
  date           date,
  valid          date,
  status_code    integer,
  status         text not null default 'draft',  -- draft | sent | accepted | declined | inv
  became_invoice integer,
  title          text,
  make           text,
  model          text,
  labour         numeric(12,2),
  parts_total    numeric(12,2),
  total          numeric(12,2),
  work           jsonb not null default '[]',  -- GarageBase work rows
  parts          jsonb not null default '[]',  -- GarageBase part rows
  lines          jsonb not null default '[]',  -- app lines [{k,d,q,p}]
  opts           jsonb not null default '[]',
  hist           jsonb not null default '[]',
  advise         jsonb not null default '[]',
  note           text not null default '',
  inote          text not null default '',
  app            jsonb not null default '{}',
  source         text not null default 'app',
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);
create index quotes_cust_idx on public.quotes (cust);
create index quotes_updated_idx on public.quotes (updated_at);
alter sequence public.quote_no_seq owned by public.quotes.no;

create sequence public.jobsheet_no_seq start with 1 no cycle;
create table public.jobsheets (
  no              integer primary key default nextval('public.jobsheet_no_seq'),
  date            date,
  reg             text,
  cust            integer references public.customers(ref) on delete set null,
  title           text,                     -- short title the app shows
  description     text,                     -- what the customer asked for
  work_done       text,
  advise          jsonb not null default '[]',
  problems        text,
  mechanic        text,
  complete        boolean not null default false,
  hours           numeric(10,2),
  hours_to_charge numeric(10,2),
  invoice         integer,
  status          text not null default 'est',  -- est | booked | ramp | ready | hold | inv
  hold            text,
  lines           jsonb not null default '[]',
  app             jsonb not null default '{}', -- who, keys, auth, miles ... (the mock's JOBS extras)
  source          text not null default 'app',
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);
create index jobsheets_reg_idx on public.jobsheets (reg);
create index jobsheets_updated_idx on public.jobsheets (updated_at);
alter sequence public.jobsheet_no_seq owned by public.jobsheets.no;

-- Diary bookings: one row per booking, the app's own record kept whole in data.
create table public.bookings (
  id         text primary key,
  day        date not null,
  data       jsonb not null,                -- {id,k,t,reg,who,...} exactly as the app holds it
  deleted    boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index bookings_day_idx on public.bookings (day) where not deleted;
create index bookings_updated_idx on public.bookings (updated_at);

create table public.day_notes (
  day        date primary key,
  notes      jsonb not null default '[]',   -- [text]
  updated_at timestamptz not null default now()
);

create table public.settings (
  key        text primary key,
  value      jsonb not null default '{}',
  updated_at timestamptz not null default now()
);

-- updated_at maintenance
create or replace function public.set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end $$;

do $$
declare t text;
begin
  foreach t in array array['customers','vehicles','invoices','payments','quotes','jobsheets','bookings','day_notes','settings'] loop
    execute format('create trigger %I_updated before update on public.%I for each row execute function public.set_updated_at()', t, t);
  end loop;
end $$;

-- Lines belong to an invoice: changing them should bump the invoice so delta sync sees it.
create or replace function public.touch_invoice() returns trigger
language plpgsql as $$
begin
  update public.invoices set updated_at = now() where no = coalesce(new.invoice_no, old.invoice_no);
  return null;
end $$;
create trigger invoice_lines_touch after insert or update or delete on public.invoice_lines
  for each row execute function public.touch_invoice();
create trigger payments_touch after insert or update or delete on public.payments
  for each row execute function public.touch_invoice();
