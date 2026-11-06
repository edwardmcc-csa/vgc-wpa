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
		secondaries: (m.secondaries || []).map(s => pick(s, EFFECT)),
	};
}
console.log(JSON.stringify({ mod: modName, moves }));
