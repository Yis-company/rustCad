// Exercise the release tool itself, without allowing network writes.
const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const {Manifest} = require('release-please/build/src/manifest');
const {buildStrategy} = require('release-please/build/src/factory');
const {Version} = require('release-please/build/src/version');
const {TagName} = require('release-please/build/src/util/tag-name');
const {parseConventionalCommits} = require('release-please/build/src/commit');
const root = path.resolve(__dirname, '../..');
const config = JSON.parse(fs.readFileSync(path.join(root, 'release-please-config.json')));
const bootstrap = config['bootstrap-sha'];
const commit = (message, sha = 'a'.repeat(40)) => ({message, sha, files: ['src/Mod/RustCad/Init.py']});

function github(messages) {
  const files = {
    'release-please-config.json': config,
    '.release-please-manifest.json': {},
  };
  return {
    repository: {owner: 'Yis-company', repo: 'rustCad', defaultBranch: 'main'},
    async getFileJson(file) { assert.ok(file in files); return files[file]; },
    async *releaseIterator() {},
    async *tagIterator() {},
    async *pullRequestIterator() {},
    async *mergeCommitIterator() {
      yield* messages.map(message => commit(message));
      yield commit('feat: inherited FreeCAD history must stop here', bootstrap);
      yield commit('feat: older history must not enter the changelog', 'b'.repeat(40));
    },
  };
}

async function strategy(stable = false) {
  const manifest = await Manifest.fromManifest(github([]), 'main');
  const options = {...manifest.repositoryConfig['.']};
  if (stable) options.prerelease = false;
  return buildStrategy({github: github([]), targetBranch: 'main', path: '.', ...options});
}

test('first release uses project config, updates only rustCad files, and excludes inherited history', async () => {
  const manifest = await Manifest.fromManifest(github(['feat: add Rust plates']), 'main');
  const [pr] = await manifest.buildPullRequests();
  assert.equal(pr.version.toString(), '0.1.0-alpha.1');
  assert.deepEqual(pr.updates.map(update => update.path).sort(),
    ['.release-please-manifest.json', 'RUSTCAD_CHANGELOG.md', 'rustcad-version.txt']);
  const version = pr.updates.find(update => update.path === 'rustcad-version.txt');
  assert.equal(version.updater.updateContent('0.0.0\n').trim(), '0.1.0-alpha.1');
  const notes = pr.updates.find(update => update.path === 'RUSTCAD_CHANGELOG.md').updater.updateContent('');
  assert.match(notes, /add Rust plates/);
  assert.doesNotMatch(notes, /inherited|older history/);
  const options = manifest.repositoryConfig['.'];
  assert.equal(options.draft, true);
  assert.equal(options.forceTag, true);
  const tag = new TagName(pr.version, options.component, options.tagSeparator, options.includeVInTag);
  assert.equal(tag.toString(), 'rustcad-v0.1.0-alpha.1');
});

test('no qualifying changes produce no release PR', async () => {
  const manifest = await Manifest.fromManifest(github(['docs: describe setup']), 'main');
  assert.deepEqual(await manifest.buildPullRequests(), []);
});

for (const message of ['fix: correct export', 'feat: support placement', 'feat!: replace a public API']) {
  test(`alpha counter: ${message}`, async () => {
    const actual = await strategy();
    const pr = await actual.buildReleasePullRequest(parseConventionalCommits([commit(message)]), {
      tag: new TagName(Version.parse('0.1.0-alpha.1'), 'rustcad', '-', true),
      sha: 'c'.repeat(40), notes: '',
    });
    assert.equal(pr.version.toString(), '0.1.0-alpha.2');
  });
}

for (const [message, expected] of [
  ['fix: correct export', '0.1.1'],
  ['feat: support another solid', '0.2.0'],
  ['feat!: replace a public API', '0.2.0'],
]) {
  test(`reviewed stable policy: ${message}`, async () => {
    const actual = await strategy(true);
    const pr = await actual.buildReleasePullRequest(parseConventionalCommits([commit(message)]), {
      tag: new TagName(Version.parse('0.1.0'), 'rustcad', '-', true),
      sha: 'c'.repeat(40), notes: '',
    });
    assert.equal(pr.version.toString(), expected);
  });
}
