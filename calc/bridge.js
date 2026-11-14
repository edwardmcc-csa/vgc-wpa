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
//        "boosts": {atk: 1, ...}, "status": "brn", "hp": 0.5 (fraction),
//        "types": ["Dark"] (optional: its types now, when changed)}
'use strict';
const readline = require('readline');
const {calculate, Generations, Pokemon, Move, Field, Side} = require('@smogon/calc');
const {getFinalSpeed} = require('@smogon/calc/dist/mechanics/util');
const mechanics = require('@smogon/calc/dist/mechanics/util');

// Week 12: a Pokemon's types now, when the game changed them (Protean, Libero,
// Soak, Burn Up ...), as "types" in MON. The calculator copies each Pokemon
// before using it, so the copy keeps them; and STAB comes from them, as in
// Showdown (the calculator otherwise gives Protean and Libero STAB on any move).
const clone0 = Pokemon.prototype.clone;
Pokemon.prototype.clone = function () {
  const c = clone0.call(this);
  if (this.typesNow) {
    c.typesNow = this.typesNow.slice();
    c.types = this.typesNow.slice();
  }
  return c;
};
const stab0 = mechanics.getStabMod;
mechanics.getStabMod = function (pokemon, move, desc) {
  if (!pokemon.typesNow) return stab0(pokemon, move, desc);
  let mod = 4096;
  if (pokemon.typesNow.includes(move.type)) {
    mod += 2048;
    if (pokemon.hasAbility('Adaptability')) mod += 2048;
  }
  return mod;
};

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
  // Supreme Overlord: the fainted allies (Week 10)
  if (m.fainted) options.alliesFainted = m.fainted;
  const name = named(gen.species, m.species, 'species');
  let p = new Pokemon(gen, name, options);
  if (m.hp !== undefined && m.hp !== null) {
    const cur = Math.max(1, Math.round(p.maxHP() * m.hp));
    p = new Pokemon(gen, name, {...options, curHP: cur});
  }
  if (Array.isArray(m.types) && m.types.length) {
    p.typesNow = m.types.slice();
    p.types = m.types.slice();
  }
  // an ability that is on now (Week 14: Flash Fire after taking in a Fire
  // move, Stakeout at one that came in this turn; Unburden for Speed)
  if (m.ability_on) p.abilityOn = true;
  return p;
}

// Week 14: the calculator's Champions rules leave out the power an ally's
// ability adds (Showdown's onAllyBasePower): Steely Spirit, Steel moves x1.5;
// Battery, special moves, and Power Spot, every move, 5325/4096. As Showdown
// chains them (4096 is x1).
function allyPower(f, move) {
  f = f || {};
  let mod = 4096;
  const chain = x => { mod = Math.floor((mod * x + 2048) / 4096); };
  if (f.steelyspirit && move.type === 'Steel') chain(6144);
  if (f.battery && move.category === 'Special') chain(5325);
  if (f.powerspot) chain(5325);
  return mod;
}

// Showdown's modify: a value times a 4096-based modifier, rounded half down
const modify = (v, mod) => Math.floor((v * mod + 2047) / 4096);

function field(f) {
  f = f || {};
  return new Field({
    gameType: 'Doubles',
    weather: f.weather || undefined,
    terrain: f.terrain || undefined,
    isFairyAura: !!f.fairyaura,
    isDarkAura: !!f.darkaura,
    isGravity: !!f.gravity,
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
  // a power the game so far decides (Last Respects, Rage Fist), worked out by
  // the caller (Week 10)
  if (req.bp) options.overrides = {...(options.overrides || {}), basePower: req.bp};
  // an ally's power (above): on the move's power, as in Showdown; on the
  // damage for a power the calculator works out itself (Gyro Ball, Heavy Slam)
  const ally = allyPower(req.field, probe);
  const power = req.bp || probe.bp;
  if (ally !== 4096 && power > 0) {
    options.overrides = {...(options.overrides || {}), basePower: modify(power, ally)};
  }
  const after = ally !== 4096 && !(power > 0) ? d => modify(d, ally) : d => d;
  const move = new Move(gen, moveName, options);
  const result = calculate(gen, attacker, defender, move, field(req.field));
  const several = Array.isArray(result.damage) && Array.isArray(result.damage[0]);
  return {
    rolls: totals(result.damage).map(after),
    hits: several ? result.damage.length : 1,
    first_hit: several ? result.damage[0].map(after) : undefined,
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
