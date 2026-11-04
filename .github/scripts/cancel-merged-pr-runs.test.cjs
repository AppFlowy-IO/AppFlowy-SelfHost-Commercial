'use strict';

const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const { resolve } = require('node:path');
const test = require('node:test');
const cancelMergedPrRuns = require('./cancel-merged-pr-runs.cjs');

const HEAD = 'a'.repeat(40);
const OLD = 'b'.repeat(40);
const ANCESTOR = 'c'.repeat(40);
const PATHS = ['backup-test.yml', 'deployment-test.yml', 'release-docker-build.yml'];

function run(id, overrides = {}) {
  return {
    id, run_attempt: 1, event: 'pull_request', status: 'in_progress',
    head_sha: HEAD, head_branch: 'feature', head_repository: { id: 10 },
    path: `.github/workflows/${PATHS[(id - 1) % PATHS.length]}`,
    created_at: '2026-11-02T12:00:00Z', pull_requests: [],
    html_url: `https://github.com/owner/repo/actions/runs/${id}`,
    ...overrides,
  };
}

function fixture(runs, options = {}) {
  const cancelled = [];
  const pages = [];
  const errors = [];
  const context = {
    eventName: 'pull_request_target', runId: 999,
    repo: { owner: 'owner', repo: 'repo' },
    payload: {
      action: 'closed', repository: { id: 10 },
      pull_request: {
        number: 54, merged: true, merged_at: '2026-11-02T13:00:00Z',
        head: { ref: 'feature', sha: HEAD, repo: { id: 10 } },
      },
    },
  };
  const actions = {
    listWorkflowRunsForRepo() {},
    async getWorkflowRun(args) {
      const original = runs.find(item => item.id === args.run_id);
      return { data: options.current ? options.current(original) : original };
    },
    async cancelWorkflowRun(args) {
      if (options.cancel) await options.cancel(args.run_id);
      cancelled.push(args.run_id);
    },
  };
  const pulls = { listCommits() {} };
  const github = {
    rest: { actions, pulls },
    async paginate(method, args) {
      pages.push(args);
      if (method === pulls.listCommits) return options.commits || [{ sha: OLD }];
      assert.equal(method, actions.listWorkflowRunsForRepo);
      return runs.filter(item => item.status === args.status);
    },
    async request(route, args) {
      assert.equal(route, 'GET /repos/{owner}/{repo}/compare/{basehead}');
      assert.equal(args.basehead, `${ANCESTOR}...${HEAD}`);
      assert.equal(args.per_page, 1);
      return { data: { status: options.comparison || 'ahead' } };
    },
  };
  const core = { info() {}, error(message) { errors.push(message); } };
  return { github, context, core, cancelled, pages, errors };
}

test('cancels every unfinished state across all three workflows and earlier PR commits', async () => {
  const statuses = ['requested', 'queued', 'pending', 'waiting', 'in_progress'];
  const f = fixture(statuses.map((status, index) => run(index + 1, {
    status, head_sha: index % 2 ? OLD : HEAD,
  })));
  assert.deepEqual(await cancelMergedPrRuns(f), [1, 2, 3, 4, 5]);
  assert.deepEqual(f.cancelled, [1, 2, 3, 4, 5]);
  assert.equal(f.pages.length, 6);
  assert.ok(f.pages.every(page => page.per_page === 100));
});

test('preserves completed, other-PR, foreign-repository, new-branch and unrelated runs', async () => {
  const f = fixture([
    run(1),
    run(2, { status: 'completed' }),
    run(3, { path: '.github/workflows/update-release-images.yml' }),
    run(4, { head_branch: 'main' }),
    run(5, { head_repository: { id: 20 } }),
    run(6, { pull_requests: [{ number: 55 }] }),
    run(7, { created_at: '2026-11-02T13:00:01Z' }),
    run(8, { head_sha: 'd'.repeat(40) }),
    run(9, { created_at: 'unknown' }),
    run(999),
  ]);
  assert.deepEqual(await cancelMergedPrRuns(f), [1]);
});

test('plain PR closure and unrelated events never query or cancel runs', async () => {
  for (const change of [
    f => { f.context.payload.pull_request.merged = false; },
    f => { f.context.payload.action = 'opened'; },
    f => { f.context.eventName = 'push'; },
  ]) {
    const f = fixture([run(1)]);
    change(f);
    assert.deepEqual(await cancelMergedPrRuns(f), []);
    assert.deepEqual(f.pages, []);
    assert.deepEqual(f.cancelled, []);
  }
});

test('missing merge metadata fails before cancellation', async () => {
  const f = fixture([run(1)]);
  f.context.payload.pull_request.merged_at = null;
  await assert.rejects(cancelMergedPrRuns(f), /missing its source identity or merge time/);
  assert.deepEqual(f.cancelled, []);
});

test('missing source-repository identity fails without cancelling a matching branch', async () => {
  const f = fixture([run(1)]);
  f.context.payload.pull_request.head.repo = null;
  await assert.rejects(cancelMergedPrRuns(f), /missing its source identity or merge time/);
  assert.deepEqual(f.cancelled, []);
});

test('fork PRs are identified by their own source repository', async () => {
  const f = fixture([run(1, { head_repository: { id: 20 } }), run(2)]);
  f.context.payload.pull_request.head.repo.id = 20;
  assert.deepEqual(await cancelMergedPrRuns(f), [1]);
});

test('completion during the identity recheck needs no cancellation', async () => {
  const f = fixture([run(1)], { current: original => ({ ...original, status: 'completed' }) });
  assert.deepEqual(await cancelMergedPrRuns(f), []);
});

test('a changed attempt is rejected while other eligible runs are still cancelled', async () => {
  const f = fixture([run(1), run(2)], {
    current: original => original.id === 1 ? { ...original, run_attempt: 2 } : original,
  });
  await assert.rejects(cancelMergedPrRuns(f), /Could not cancel all merged-PR runs: 1/);
  assert.deepEqual(f.cancelled, [2]);
});

test('a changed source revision is rejected', async () => {
  const f = fixture([run(1)], { current: original => ({ ...original, head_sha: OLD }) });
  await assert.rejects(cancelMergedPrRuns(f), /Could not cancel all merged-PR runs: 1/);
  assert.deepEqual(f.cancelled, []);
});

test('a 409 race is harmless only after completion is verified', async () => {
  for (const completed of [false, true]) {
    let requested = false;
    const f = fixture([run(1)], {
      current: original => requested && completed ? { ...original, status: 'completed' } : original,
      cancel() { requested = true; throw Object.assign(new Error('Conflict'), { status: 409 }); },
    });
    if (completed) assert.deepEqual(await cancelMergedPrRuns(f), []);
    else await assert.rejects(cancelMergedPrRuns(f), /Could not cancel all merged-PR runs: 1/);
  }
});

test('permission errors are reported without stopping cancellation of other runs', async () => {
  const f = fixture([run(1), run(2)], {
    cancel(id) {
      if (id === 1) throw Object.assign(new Error('Forbidden'), { status: 403 });
    },
  });
  await assert.rejects(cancelMergedPrRuns(f), /Could not cancel all merged-PR runs: 1/);
  assert.deepEqual(f.cancelled, [2]);
});

test('release builds started before the PR need verified source ancestry', async () => {
  for (const comparison of ['ahead', 'identical', 'behind', 'diverged']) {
    const f = fixture([run(3, {
      event: 'create', head_sha: ANCESTOR, head_branch: 'release/public/0.20.4',
    })], { comparison });
    f.context.payload.pull_request.head.ref = 'release/public/0.20.4';
    const expected = ['ahead', 'identical'].includes(comparison) ? [3] : [];
    assert.deepEqual(await cancelMergedPrRuns(f), expected);
  }
});

const workflows = JSON.parse(execFileSync('python3', ['-c', `
import json, pathlib, yaml
root = pathlib.Path(${JSON.stringify(resolve(__dirname, '..', 'workflows'))})
print(json.dumps({p.stem: yaml.load(p.read_text(), Loader=yaml.BaseLoader)
                 for p in root.glob('*.yml')}))
`], { encoding: 'utf8' }));

test('merge cleanup is unfiltered and executes only trusted base code with scoped permissions', () => {
  const workflow = workflows['cancel-merged-pr-runs'];
  assert.deepEqual(workflow.on, { pull_request_target: { types: ['closed'] } });
  assert.equal(workflow.jobs.cancel.if, 'github.event.pull_request.merged == true');
  assert.deepEqual(workflow.permissions, {
    actions: 'write', contents: 'read', 'pull-requests': 'read',
  });
  const checkout = workflow.jobs.cancel.steps.find(step => step.uses?.startsWith('actions/checkout@'));
  assert.equal(checkout.with.ref, '${{ github.sha }}');
  assert.equal(checkout.with['persist-credentials'], 'false');
});

test('existing README filters and release-only build triggers remain active', () => {
  for (const name of ['backup-test', 'deployment-test']) {
    for (const event of ['pull_request', 'push']) {
      assert.deepEqual(workflows[name].on[event]['paths-ignore'], ['README.md', 'docs/**']);
    }
    assert.ok(Object.hasOwn(workflows[name].on, 'workflow_dispatch'));
  }
  assert.deepEqual(Object.keys(workflows['release-docker-build'].on), ['create']);
  assert.equal(workflows['release-docker-build'].jobs['docker-build'].if,
    "!cancelled() && github.event.ref_type == 'branch' && startsWith(github.event.ref, 'release/public/')");
  assert.equal(workflows['deployment-test'].jobs['deployment-tests'].if, 'always() && !cancelled()');
});

const cleanup = workflows['release-docker-build'].jobs['docker-build'].steps.find(
  step => step.name === 'Cancel the dispatched Docker build when this run is cancelled');
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

test('release cancellation reaches only its exact downstream run and ignores completed builds', async () => {
  assert.equal(cleanup.if, "cancelled() && steps.dispatch.outputs.run-id != ''");
  for (const status of ['queued', 'in_progress', 'completed']) {
    const calls = [];
    const actions = {
      async getWorkflowRun(args) {
        assert.deepEqual(args, { owner: 'AppFlowy-IO', repo: 'AppFlowy-Docker-CI', run_id: 123 });
        return { data: { status } };
      },
      async cancelWorkflowRun(args) { calls.push(args.run_id); },
    };
    await new AsyncFunction('github', 'core', 'process', cleanup.with.script)(
      { rest: { actions } }, { info() {} }, { env: { DOCKER_BUILD_RUN_ID: '123' } });
    assert.deepEqual(calls, status === 'completed' ? [] : [123]);
  }
});

test('an invalid downstream run ID cannot reach the API', async () => {
  await assert.rejects(new AsyncFunction('github', 'core', 'process', cleanup.with.script)(
    {}, {}, { env: { DOCKER_BUILD_RUN_ID: 'invalid' } }), /Missing or invalid Docker CI run ID/);
});
