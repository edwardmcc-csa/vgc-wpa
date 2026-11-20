// Dump the species, move and item facts the team-sheet features need, as JSON.
//
//   node scripts/dump_dex.js <showdown-dir> <mod>
//
// Reads Showdown's compiled data (dist/) for one mod after inheritance, like
// scripts/dump_durations.js. Interprets nothing.
'use strict';
const path = require('path');

const [, , root, modName] = process.argv;
if (!root || !modName) {
	console.error('usage: node dump_dex.js <showdown-dir> <mod>');
	process.exit(2);
}
const { Dex } = require(path.join(path.resolve(root), 'dist/sim/dex'));
const dex = Dex.mod(modName);

const species = {};
for (const s of dex.species.all()) {
	species[s.id] = {
		name: s.name,
		baseSpecies: s.baseSpecies,
		forme: s.forme || '',
		types: s.types,
		baseStats: s.baseStats,
		abilities: s.abilities,
		isMega: !!s.isMega,
		requiredItem: s.requiredItem || null,
		requiredItems: s.requiredItems || null,
	};
}
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
		priority: m.priority,
		target: m.target,
		type: m.type,
		flags: Object.keys(m.flags || {}),
		pp: battlePP(m),
	};
}
const items = {};
for (const it of dex.items.all()) {
	items[it.id] = { name: it.name, megaStone: it.megaStone || null };
}
const abilities = {};
for (const a of dex.abilities.all()) abilities[a.id] = { name: a.name, flags: a.flags };
console.log(JSON.stringify({ mod: modName, species, moves, items, abilities }));
