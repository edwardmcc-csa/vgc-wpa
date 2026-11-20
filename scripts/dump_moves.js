// Dump the move facts the turn resolver needs (Week 9 Task 2), as JSON.
//
//   node scripts/dump_moves.js <showdown-dir> <mod>
//
// Reads Showdown's compiled data (dist/) for one mod after inheritance, like
// scripts/dump_dex.js. Interprets nothing: fields are copied as Showdown has them.
'use strict';
const path = require('path');

const [, , root, modName] = process.argv;
if (!root || !modName) {
	console.error('usage: node dump_moves.js <showdown-dir> <mod>');
	process.exit(2);
}
const { Dex } = require(path.join(path.resolve(root), 'dist/sim/dex'));
const dex = Dex.mod(modName);

const pick = (obj, keys) => {
	if (!obj) return null;
	const out = {};
	for (const k of keys) if (obj[k] !== undefined) out[k] = obj[k];
	return out;
};
const EFFECT = ['chance', 'status', 'boosts', 'volatileStatus', 'self'];
// A move's PP in battle, as the format's own rule gives it (Week 17): Showdown's
// calculatePP with 3 PP Ups (none for a move that takes none), or the mod's own
// (Champions: (pp / 5 + 1) x 4).
const scripts = (dex.data && dex.data.Scripts) || {};
const battlePP = m => {
	const ups = m.noPPBoosts || m.id === 'trumpcard' ? 0 : 3;
	if (typeof scripts.calculatePP === 'function') {
		return scripts.calculatePP.call({ gen: dex.gen }, m, ups);
	}
	if (m.noPPBoosts) return m.pp;
	let pp = (m.pp * (5 + ups)) / 5;
	if (dex.gen <= 2 && m.pp === 40) pp -= ups;
	return pp;
};
const moves = {};
for (const m of dex.moves.all()) {
	moves[m.id] = {
		name: m.name,
		category: m.category,
		basePower: m.basePower,
		accuracy: m.accuracy, // true: never misses
		priority: m.priority,
		target: m.target,
		nonGhostTarget: m.nonGhostTarget || null,
		type: m.type,
		flags: Object.keys(m.flags || {}),
		critRatio: m.critRatio || 1,
		willCrit: !!m.willCrit,
		multihit: m.multihit || null,
		drain: m.drain || null,
		recoil: m.recoil || null,
		heal: m.heal || null,
		boosts: m.boosts || null,
		status: m.status || null,
		volatileStatus: m.volatileStatus || null,
		sideCondition: m.sideCondition || null,
		weather: m.weather || null,
		terrain: m.terrain || null,
		pseudoWeather: m.pseudoWeather || null,
		selfSwitch: m.selfSwitch || null,
		forceSwitch: !!m.forceSwitch,
		selfdestruct: m.selfdestruct || null,
		breaksProtect: !!m.breaksProtect,
		stallingMove: !!m.stallingMove,
		ohko: m.ohko || null,
		self: pick(m.self, ['boosts', 'volatileStatus']),
		pp: battlePP(m),
		secondaries: (m.secondaries || []).map(s => pick(s, EFFECT)),
	};
}
console.log(JSON.stringify({ mod: modName, moves }));
