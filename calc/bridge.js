// Bridge to the Smogon damage calculator (@smogon/calc, pinned in package.json).
// One JSON request per line on stdin, one JSON answer per line on stdout, in
// order. Names are given as Showdown ids and resolved here.
//
//   {"attacker": MON, "defender": MON, "move": "kowtowcleave",
//    "spread": false, "crit": false, "field": {...}}
//     -> {"rolls": [16 numbers], "max_hp": n, "cur_hp": n}
//   {"op": "stats", "mon": MON} -> {"stats": {"hp": n, "atk": n, ...}}
//
// MON = {"species", "nature", "sps": {hp, atk, ...}, "item", "ability",
//        "boosts": {atk: 1, ...}, "status": "brn", "hp": 0.5 (fraction)}
'use strict';
const readline = require('readline');
const {calculate, Generations, Pokemon, Move, Field, Side} = require('@smogon/calc');
const {getFinalSpeed} = require('@smogon/calc/dist/mechanics/util');

const gen = Generations.get(0); // Champions: level 50, stat points
const SPREAD = new Set(['allAdjacent', 'allAdjacentFoes']);

const toID = s => String(s).toLowerCase().replace(/[^a-z0-9]/g, '');
// Showdown names a few default forms by the bare species; the calculator does not
const ALIASES = {aegislash: 'aegislashshield'};

function named(table, name, what) {
  if (!name) return undefined;
  const id = toID(name);
  let x = table.get(id) || (ALIASES[id] && table.get(ALIASES[id]));
  if (!x && what === 'species') {
    // a cosmetic form the calculator does not list (Vivillon-Garden,
    // Alcremie-Rainbow-Swirl): the longest species id the name starts with
    for (let k = id.length - 1; k >= 3 && !x; k--) x = table.get(id.slice(0, k));
  }
  if (!x) throw new Error(`unknown ${what}: ${name}`);
  return x.name;
}

function mon(m, attacking) {
  m = {...m};
  // Stance Change: Aegislash attacks in its Blade form
  if (attacking && toID(m.ability) === 'stancechange' && toID(m.species).startsWith('aegislash')) {
    m.species = 'aegislashblade';
  }
  const options = {
    nature: named(gen.natures, m.nature || 'serious', 'nature'),
    evs: m.sps || {},
    item: named(gen.items, m.item, 'item'),
    ability: named(gen.abilities, m.ability, 'ability'),
    boosts: m.boosts || {},
    status: m.status || '',
  };
  const name = named(gen.species, m.species, 'species');
  let p = new Pokemon(gen, name, options);
  if (m.hp !== undefined && m.hp !== null) {
    const cur = Math.max(1, Math.round(p.maxHP() * m.hp));
    p = new Pokemon(gen, name, {...options, curHP: cur});
  }
  return p;
}

function field(f) {
  f = f || {};
  return new Field({
    gameType: 'Doubles',
    weather: f.weather || undefined,
    terrain: f.terrain || undefined,
    isFairyAura: !!f.fairyaura,
    isDarkAura: !!f.darkaura,
    defenderSide: {
      isReflect: !!f.reflect,
      isLightScreen: !!f.lightscreen,
      isAuroraVeil: !!f.auroraveil,
      isFriendGuard: !!f.friendguard,
    },
    attackerSide: {
      isHelpingHand: !!f.helpinghand,
      isBattery: !!f.battery,
      isPowerSpot: !!f.powerspot,
      isSteelySpirit: !!f.steelyspirit,
      isFlowerGift: !!f.flowergift,
    },
  });
}

function totals(damage) {
  if (typeof damage === 'number') return Array(16).fill(damage);
  if (damage.length && Array.isArray(damage[0])) {
    // several hits: add them up roll by roll
    const out = Array(damage[0].length).fill(0);
    for (const hit of damage) hit.forEach((d, i) => { out[i] += d; });
    return out;
  }
  return damage.slice();
}

// Moves whose damage does not depend on stats, which the calculator's Champions
// rules leave at 0: computed here from hit points or level (Champions: 50).
// Moves that return damage taken (Counter, Mirror Coat ...) and Beat Up (one hit
// per healthy party member, which the calculator does not model) are unknown.
const FIXED = {
  superfang: (a, d) => Math.max(1, Math.floor(d.curHP() / 2)),
  ruination: (a, d) => Math.max(1, Math.floor(d.curHP() / 2)),
  naturesmadness: (a, d) => Math.max(1, Math.floor(d.curHP() / 2)),
  endeavor: (a, d) => Math.max(0, d.curHP() - a.curHP()),
  seismictoss: () => 50,
  nightshade: () => 50,
  finalgambit: a => a.curHP(),
};
const RETURNED = new Set(['counter', 'mirrorcoat', 'metalburst', 'comeuppance', 'bide', 'beatup']);

function immune(move, attacker, defender) {
  // the type chart only: Ghost against Normal and Fighting, Normal against Ghost
  if (attacker.hasAbility('Scrappy', "Mind's Eye") && defender.hasType('Ghost')) {
    return false;
  }
  const t = gen.types.get(toID(move.type));
  return defender.types.some(dt => t.effectiveness[dt] === 0);
}

function answer(req) {
  if (req.op === 'stats') {
    return {stats: mon(req.mon).rawStats};
  }
  if (req.op === 'speed') {
    const p = mon(req.mon, false);
    if (req.mon.ability_on) p.abilityOn = true;
    return {speed: getFinalSpeed(gen, p, field(req.field), new Side({isTailwind: !!req.tailwind}))};
  }
  const attacker = mon(req.attacker, true);
  const defender = mon(req.defender, false);
  const moveName = named(gen.moves, req.move, 'move');
  const moveId = toID(moveName);
  if (FIXED[moveId] || RETURNED.has(moveId)) {
    const m = new Move(gen, moveName);
    const known = !RETURNED.has(moveId);
    const d = !known || immune(m, attacker, defender) ? 0 : FIXED[moveId](attacker, defender);
    const out = {rolls: Array(16).fill(d), max_hp: defender.maxHP(), cur_hp: defender.curHP()};
    if (!known) out.unknown = true;
    return out;
  }
  const probe = new Move(gen, moveName);
  const options = {isCrit: !!req.crit};
  if (SPREAD.has(probe.target) && !req.spread) options.overrides = {target: 'normal'};
  const move = new Move(gen, moveName, options);
  const result = calculate(gen, attacker, defender, move, field(req.field));
  const several = Array.isArray(result.damage) && Array.isArray(result.damage[0]);
  return {
    rolls: totals(result.damage),
    hits: several ? result.damage.length : 1,
    first_hit: several ? result.damage[0].slice() : undefined,
    max_hp: defender.maxHP(),
    cur_hp: defender.curHP(),
    species: [attacker.name, defender.name],
  };
}

module.exports = {answer, gen};

if (require.main === module) {
  const rl = readline.createInterface({input: process.stdin, terminal: false});
  rl.on('line', line => {
    let out;
    try {
      out = answer(JSON.parse(line));
    } catch (e) {
      out = {error: String(e && e.message ? e.message : e)};
    }
    process.stdout.write(JSON.stringify(out) + '\n');
  });
}
