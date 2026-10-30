// Check the damage calculator against Showdown's own damage code (Week 7 Task 2).
//
//   node calc/check_showdown.js <showdown-dir> <cases.json> <out.json>
//
// For each case (the same request the bridge takes, plus "format"), builds a
// Showdown battle with the two Pokemon, sets the stages, status, hit points,
// weather, terrain and screens, and asks Showdown's getDamage for every one of
// its 16 random rolls, critical hit decided by the case. Nothing in Showdown is
// edited: its random roll is replaced on the battle object only.
'use strict';
const path = require('path');
const fs = require('fs');
const {answer} = require('./bridge');

const [, , root, casesPath, outPath] = process.argv;
const {Battle} = require(path.join(path.resolve(root), 'dist/sim/battle'));
const {Dex} = require(path.join(path.resolve(root), 'dist/sim/dex'));

const WEATHER = {Sun: 'sunnyday', Rain: 'raindance', Sand: 'sandstorm', Snow: 'snowscape'};
const TERRAIN = {
  Electric: 'electricterrain', Grassy: 'grassyterrain',
  Psychic: 'psychicterrain', Misty: 'mistyterrain',
};
const FILLER = {species: 'Rattata', ability: 'Run Away', item: '', moves: ['tackle'],
  nature: 'Serious', evs: {}, level: 50, gender: 'M'};

function set(m, move, dex) {
  return {
    name: 'x' + Math.random().toString(36).slice(2, 7),
    species: dex.species.get(m.base_species || m.species).name,
    item: m.item ? dex.items.get(m.item).name : '',
    ability: dex.abilities.get(m.base_ability || m.ability).name,
    moves: [move],
    nature: dex.natures.get(m.nature || 'serious').name,
    evs: m.sps || {},
    level: 50,
    gender: 'M',
  };
}

function showdown(c) {
  const dex = Dex.forFormat(c.format);
  const move0 = dex.moves.get(c.move);
  if (move0.category === 'Status') return {skip: 'status move'};
  if (move0.ohko) return {skip: 'one-hit knock-out'};
  const abil = [c.attacker.ability, c.defender.ability].map(a => dex.abilities.get(a).id);
  if (abil.includes('imposter')) return {skip: 'Imposter (copies a Pokemon this check does not place)'};
  const battle = new Battle({formatid: c.format, seed: [1, 2, 3, 4]});
  battle.setPlayer('p1', {name: 'a', team: [set(c.attacker, c.move, dex), FILLER]});
  battle.setPlayer('p2', {name: 'b', team: [set(c.defender, 'tackle', dex), FILLER]});
  battle.makeChoices('team 12', 'team 12');
  const att = battle.p1.active[0];
  const def = battle.p2.active[0];
  for (const [p, m] of [[att, c.attacker], [def, c.defender]]) {
    if (m.base_species && m.base_species !== m.species) {
      p.formeChange(dex.species.get(m.species).name, p.getItem(), true);
    }
  }
  battle.field.clearWeather();
  battle.field.clearTerrain();
  const f = c.field || {};
  if (f.weather) battle.field.setWeather(WEATHER[f.weather], att);
  if (f.terrain) battle.field.setTerrain(TERRAIN[f.terrain], att);
  if (f.reflect) battle.p2.addSideCondition('reflect', def);
  if (f.lightscreen) battle.p2.addSideCondition('lightscreen', def);
  if (f.auroraveil) battle.p2.addSideCondition('auroraveil', def);
  for (const [p, m] of [[att, c.attacker], [def, c.defender]]) {
    p.clearBoosts();
    for (const [k, v] of Object.entries(m.boosts || {})) p.boosts[k] = v;
    p.status = m.status || '';
    if (m.hp !== undefined && m.hp !== null) p.hp = Math.max(1, Math.round(p.maxhp * m.hp));
  }
  const items = [att.item, def.item];
  const rolls = [];
  for (let r = 15; r >= 0; r--) {
    battle.randomizer = d => Math.trunc(Math.trunc(d * (100 - r)) / 100);
    // a berry eaten by one roll must be there for the next
    att.item = items[0];
    def.item = items[1];
    let move = dex.getActiveMove(c.move);
    if (c.crit) move.willCrit = true;
    else if (!move.willCrit) move.willCrit = false; // always-critical moves stay so
    if (['meteorbeam', 'electroshot'].includes(move.id)) {
      // the charging turn raises Special Attack before the hit
      att.boosts.spa = Math.min(6, ((c.attacker.boosts || {}).spa || 0) + 1);
    }
    if (c.spread) move.spreadHit = true;
    move.hit = 1; // several hits: the first one is compared
    // what Showdown does before a move hits: type changes (Pixilate, Weather
    // Ball, Liquid Voice, Raging Bull) and other move changes
    battle.setActiveMove(move, att, def);
    battle.singleEvent('ModifyType', move, null, att, def, move, move);
    battle.singleEvent('ModifyMove', move, null, att, def, move, move);
    move = battle.runEvent('ModifyType', att, def, move, move);
    move = battle.runEvent('ModifyMove', att, def, move, move);
    // Protean and Libero change the user's type here
    battle.singleEvent('PrepareHit', move, {}, def, att, move);
    battle.runEvent('PrepareHit', att, def, move);
    const d = battle.actions.getDamage(att, def, move, true);
    rolls.push(typeof d === 'number' ? d : 0);
  }
  const several = !!move0.multihit || abil[0] === 'parentalbond';
  return {rolls, max_hp: def.maxhp, first_hit_only: several};
}

const cases = JSON.parse(fs.readFileSync(casesPath, 'utf8'));
const out = [];
for (const c of cases) {
  let sd, calc;
  try { sd = showdown(c); } catch (e) { sd = {error: String(e.message || e)}; }
  try { calc = answer(c); } catch (e) { calc = {error: String(e.message || e)}; }
  out.push({case: c, showdown: sd, calc});
}
fs.writeFileSync(outPath, JSON.stringify(out));
console.log(`checked ${out.length} cases`);
