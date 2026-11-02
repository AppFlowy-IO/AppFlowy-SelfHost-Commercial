'use strict';

const WORKFLOWS = new Set([
  '.github/workflows/backup-test.yml',
  '.github/workflows/deployment-test.yml',
  '.github/workflows/release-docker-build.yml',
]);
const ACTIVE = ['requested', 'queued', 'pending', 'waiting', 'in_progress'];

module.exports = async function cancelMergedPrRuns({ github, context, core }) {
  const pr = context.payload.pull_request;
  if (context.eventName !== 'pull_request_target' || context.payload.action !== 'closed' ||
      pr?.merged !== true) {
    return [];
  }
  const mergedAt = Date.parse(pr.merged_at);
  if (!pr.head?.ref || !pr.head?.repo?.id || !pr.head?.sha || !Number.isFinite(mergedAt)) {
    throw new Error('Merged PR is missing its source identity or merge time.');
  }
  const { owner, repo } = context.repo;
  const commits = await github.paginate(github.rest.pulls.listCommits, {
    owner, repo, pull_number: pr.number, per_page: 100,
  });
  const revisions = new Set([pr.head.sha, ...commits.map(commit => commit.sha)]);

  async function belongsToPr(run) {
    const path = run.path?.split('@')[0];
    if (!ACTIVE.includes(run.status) || run.id === context.runId ||
        !WORKFLOWS.has(path) || run.head_branch !== pr.head.ref ||
        !(Date.parse(run.created_at) <= mergedAt)) {
      return false;
    }
    const associations = run.pull_requests || [];
    if (associations.length && !associations.some(item => item.number === pr.number)) {
      return false;
    }
    if (!pr.head.repo?.id || run.head_repository?.id !== pr.head.repo.id) {
      return false;
    }
    // GitHub can return an empty pull_requests array, including for same-repository PRs.
    if (revisions.has(run.head_sha)) {
      return ['pull_request', 'push', 'create', 'workflow_dispatch'].includes(run.event);
    }
    // A release branch can be created before its first PR commit. Verify that build's exact
    // revision is an ancestor of the merged head rather than relying on the branch name alone.
    if (run.event !== 'create' || path !== '.github/workflows/release-docker-build.yml' ||
        pr.head.repo.id !== context.payload.repository.id ||
        !pr.head.ref.startsWith('release/public/') || !/^[0-9a-f]{40}$/i.test(run.head_sha)) {
      return false;
    }
    const { data } = await github.request('GET /repos/{owner}/{repo}/compare/{basehead}', {
      owner, repo, basehead: `${run.head_sha}...${pr.head.sha}`, per_page: 1,
    });
    return data.status === 'ahead' || data.status === 'identical';
  }

  const snapshots = new Map();
  for (const status of ACTIVE) {
    const runs = await github.paginate(github.rest.actions.listWorkflowRunsForRepo, {
      owner, repo, branch: pr.head.ref, status, per_page: 100,
    });
    for (const run of runs) snapshots.set(run.id, run);
  }

  const cancelled = [];
  const failures = [];
  for (const snapshot of snapshots.values()) {
    try {
      if (!await belongsToPr(snapshot)) continue;
      const args = { owner, repo, run_id: snapshot.id };
      const { data: current } = await github.rest.actions.getWorkflowRun(args);
      if (current.status === 'completed') continue;
      if (current.id !== snapshot.id || current.head_sha !== snapshot.head_sha ||
          current.run_attempt !== snapshot.run_attempt || !await belongsToPr(current)) {
        throw new Error('Run identity or attempt changed before cancellation.');
      }
      try {
        await github.rest.actions.cancelWorkflowRun(args);
      } catch (error) {
        if (error.status !== 409) throw error;
        const { data: raced } = await github.rest.actions.getWorkflowRun(args);
        if (raced.status !== 'completed') throw error;
        continue;
      }
      core.info(`Requested cancellation of ${current.html_url}`);
      cancelled.push(current.id);
    } catch (error) {
      core.error(`Run ${snapshot.id}: ${error.message}`);
      failures.push(snapshot.id);
    }
  }
  if (failures.length) {
    throw new Error(`Could not cancel all merged-PR runs: ${failures.join(', ')}`);
  }
  core.info(`Requested ${cancelled.length} cancellation(s) for merged PR #${pr.number}.`);
  return cancelled;
};
