-- 0026  R3 - re-point process-setting applicability onto Application Area
--
-- Charlie's R3 handover v3, section 3: "Convert the 37 method-only rows to
-- Application Area defaults with no Production Unit reference. Convert the 9
-- machine-plus-method rows to Machine + Application Area. Keep the 4 global
-- rows global. Do not fan the 37 Application Area defaults out across every
-- Production Unit."
--
-- THE DESTINATIONS, AND WHERE THEY COME FROM
--
--   PM-100  Discontinuous Panel & Board Production  ->  APP-210
--   PM-800  Discontinuous Appliance & Cavity Foaming ->  APP-310
--
-- Each plant running the method has exactly one Product Grade, and that grade
-- carries the Application Area: HTC Phase 1's RF-COLDROOM-001 is APP-210 and
-- PTU Korat's RF-Refrigerator-001 is APP-310. The mapping is resolved by
-- LOOKING THE ROWS UP rather than by hard-coded ids, so the artifact is
-- readable and cannot silently point at the wrong record on a probe.
--
-- This is test data. A real deployment re-derives its own mapping the same way
-- and does not inherit these two pairs.
--
-- WHAT CHANGES ON EACH ROW
--
-- production_method_id is CLEARED on every converted row. A row keeping both
-- would apply only where method AND area both match, which is a Method +
-- Application Area rule - not the inherited default Charlie asked for. The
-- legacy column itself stays until Production Method retirement, as Plan v5
-- sequences it; what goes is the reference on these rows.
--
-- No Production Unit / Cell reference is written anywhere. That is the "do not
-- fan out" instruction, and it is also what makes the unit tier useful later:
-- a unit row means "this line differs", and it cannot mean that if every unit
-- already has one.
--
-- The 4 global rows are not touched. They are absent from every WHERE clause
-- below rather than excluded by a condition, which is a stronger guarantee
-- than a filter somebody could edit.

-- Step 1 - the 37 method-only rows become Application Area defaults.
update process_setting_applicabilities a
   set application_id = ap.id,
       production_method_id = null
  from production_methods pm, applications ap
 where pm.id = a.production_method_id
   and a.machine_id is null
   and (
        (pm.controlled_id = 'PM-100' and ap.controlled_id = 'APP-210')
     or (pm.controlled_id = 'PM-800' and ap.controlled_id = 'APP-310')
   );

-- Step 2 - the 9 machine-plus-method rows become Machine + Application Area.
-- Same mapping, machine_id untouched.
update process_setting_applicabilities a
   set application_id = ap.id,
       production_method_id = null
  from production_methods pm, applications ap
 where pm.id = a.production_method_id
   and a.machine_id is not null
   and (
        (pm.controlled_id = 'PM-100' and ap.controlled_id = 'APP-210')
     or (pm.controlled_id = 'PM-800' and ap.controlled_id = 'APP-310')
   );

do $$
declare n integer; offenders text;
begin
    -- Nothing may be left pointing at a Production Method. If a method turns
    -- up here that has no destination in the mapping above, this raises rather
    -- than leaving a half-converted table - the state 0024's own exit check
    -- was written to refuse.
    select string_agg(distinct pm.controlled_id, ', ') into offenders
      from process_setting_applicabilities a
      join production_methods pm on pm.id = a.production_method_id;
    if offenders is not null then
        raise exception 'Applicability rows still reference Production Method(s) %: no Application Area destination.', offenders;
    end if;

    -- Every converted row carries an Application Area.
    select count(*) into n from process_setting_applicabilities
     where application_id is null and machine_id is null;
    if n <> 4 then
        raise exception 'Expected exactly 4 global rows after conversion, found %.', n;
    end if;

    select count(*) into n from process_setting_applicabilities
     where application_id is not null and machine_id is null;
    if n <> 37 then
        raise exception 'Expected 37 Application Area default rows, found %.', n;
    end if;

    select count(*) into n from process_setting_applicabilities
     where application_id is not null and machine_id is not null;
    if n <> 9 then
        raise exception 'Expected 9 Machine + Application Area rows, found %.', n;
    end if;

    -- The "do not fan out" instruction, asserted rather than trusted.
    select count(*) into n from process_setting_applicabilities
     where production_unit_id is not null;
    if n <> 0 then
        raise exception '% row(s) carry a Production Unit / Cell reference. 0026 writes none.', n;
    end if;

    -- Total unchanged: this is a re-pointing, not a rewrite.
    select count(*) into n from process_setting_applicabilities;
    if n <> 50 then
        raise exception 'Applicability row count is % - a re-pointing must not add or remove rows.', n;
    end if;

    raise notice 'R3: applicability re-pointed to Application Area in %. 37 defaults, 9 machine-scoped, 4 global.', current_schema();
end $$;
