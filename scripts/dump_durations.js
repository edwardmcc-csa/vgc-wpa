// Dump every timed or counted effect from a Pokemon Showdown mod, as JSON.
//
//   node scripts/dump_durations.js <showdown-dir> <mod>
//
// This reads Showdown's own compiled data (dist/), after its mod inheritance
// has been resolved, so what comes out is exactly what the simulator runs for
// that mod. It interprets nothing: durations, callback source text and the
// move fields that attach an effect are written out verbatim. wpa/durations.py
// parses this and finds each piece's line in the TypeScript source.
'use strict';
const path = require('path');

const [, , root, modName] = process.argv;
if (!root || !modName) {
	console.error('usage: node dump_durations.js <showdown-dir> <mod>');
	process.exit(2);
}
const { Dex } = require(path.join(path.resolve(root), 'dist/sim/dex'));
const data = Dex.mod(modName).data;

const ATTACH_FIELDS = [
	'sideCondition', 'pseudoWeather', 'terrain', 'weather', 'volatileStatus', 'slotCondition', 'status',
];
// A function is worth recording when it sets, adjusts or counts a length.
const COUNTS = /\bduration\b|startTime|trueDuration|endingTurn|startingTurn|effectState\.(time|counter|stage)|statusState\.(time|stage)|\.stage\b|randomChance\(|this\.random\(|this\.sample\(/;

function functionsOf(owner, obj, out) {
	for (const key of Object.keys(obj)) {
		if (typeof obj[key] === 'function' && COUNTS.test(obj[key].toString())) {
			out[`${owner}.${key}`] = obj[key].toString();
		}
	}
}

const rows = [];
for (const table of ['Conditions', 'Moves', 'Abilities', 'Items']) {
	for (const id of Object.keys(data[table])) {
		const entry = data[table][id];
		const cond = table === 'Conditions' ? entry : entry.condition;
		const functions = {};
		if (table !== 'Conditions') functionsOf('entry', entry, functions);
		if (cond) functionsOf('condition', cond, functions);
		const timed = !!cond && (cond.duration !== undefined || !!cond.durationCallback);
		if (!timed && Object.keys(functions).length === 0) continue;
		const attach = {};
		if (table !== 'Conditions') {
			for (const f of ATTACH_FIELDS) if (entry[f] !== undefined) attach[f] = entry[f];
		}
		rows.push({
			table,
			id,
			name: entry.name || id,
			effectType: cond && cond.effectType ? cond.effectType : entry.effectType || null,
			attach,
			duration: cond && cond.duration !== undefined ? cond.duration : null,
			durationCallback: cond && cond.durationCallback ? cond.durationCallback.toString() : null,
			functions,
		});
	}
}
console.log(JSON.stringify({ mod: modName, effects: rows }));
