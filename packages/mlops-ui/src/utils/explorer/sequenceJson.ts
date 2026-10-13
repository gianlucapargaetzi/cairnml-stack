// Sequences (images, audio, text, figures, distributions) arrive as JSON from
// /api/v1/explorer/runs/search/<kind>. The models read each run as a list of traces, one per
// sequence, with the values of each sampled step grouped together. This module reshapes the JSON
// into that layout. The item fields keep the names the models already read.

import { IExplorerRunProps, toRunProps } from './explorerJson';

export type ExplorerSequenceKind =
  | 'image'
  | 'audio'
  | 'text'
  | 'figure'
  | 'distribution';

export interface IExplorerSequenceItem {
  step: number | null;
  idx: number;
  epoch: number | null;
  ts: number;
  caption: string | null;
  format: string | null;
  width: number | null;
  height: number | null;
  // Presigned GET for image and audio items.
  blob_uri?: string | null;
  text?: string;
  data?: unknown;
}

export interface IExplorerSequence {
  name: string;
  context: { [key: string]: unknown };
  count: number;
  items: IExplorerSequenceItem[];
}

// The step and index ranges the sliders read; see the server's explorer docs.
export interface IExplorerSequenceRanges {
  record_range_total: number[];
  index_range_total: number[];
  record_range_used: number[];
  index_range_used: number[];
}

export interface IExplorerSequenceRun {
  props: IExplorerRunProps;
  params: { [key: string]: any };
  sequences: IExplorerSequence[];
  ranges: IExplorerSequenceRanges;
}

export interface IExplorerSequenceSearch {
  runs: { [runId: string]: IExplorerSequenceRun };
  progress: [number, number];
}

// One stored value of a step, as the item components read it.
export interface ISequenceRecord {
  index: number;
  caption: string;
  format: string;
  width: number | null;
  height: number | null;
  blob_uri?: string | null;
  text?: string;
  data?: unknown;
}

export interface ISequenceTrace {
  name: string;
  context: { [key: string]: unknown };
  count: number;
  iters: number[];
  values: ISequenceRecord[][];
}

export interface ISequenceRun {
  hash: string;
  params: { [key: string]: any };
  props: ReturnType<typeof toRunProps>;
  created_at: number;
  ranges: IExplorerSequenceRanges;
  traces: ISequenceTrace[];
}

const NO_STEP = -1;

function toRecord(item: IExplorerSequenceItem): ISequenceRecord {
  const record: ISequenceRecord = {
    index: item.idx,
    caption: item.caption ?? '',
    format: item.format ?? '',
    width: item.width,
    height: item.height,
  };
  if (item.blob_uri != null) {
    record.blob_uri = item.blob_uri;
  }
  if (item.text !== undefined) {
    record.text = item.text;
  }
  if (item.data !== undefined) {
    record.data = item.data;
  }
  return record;
}

function toTrace(sequence: IExplorerSequence): ISequenceTrace {
  const byStep = new Map<number, IExplorerSequenceItem[]>();
  for (const item of sequence.items) {
    const step = item.step ?? NO_STEP;
    byStep.set(step, [...(byStep.get(step) ?? []), item]);
  }
  const iters = [...byStep.keys()].sort((a, b) => a - b);
  return {
    name: sequence.name,
    context: sequence.context,
    count: sequence.count,
    iters,
    values: iters.map((step) => (byStep.get(step) ?? []).map(toRecord)),
  };
}

// The run as the sequence models read it. The kind is kept for callers that need to tell the
// explorers apart; the shape is the same for all of them.
export function toSequenceRun(
  runId: string,
  run: IExplorerSequenceRun,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  kind: ExplorerSequenceKind,
): ISequenceRun {
  return {
    hash: runId,
    params: run.params,
    props: toRunProps(run.props),
    created_at: run.props.creation_time,
    ranges: run.ranges,
    traces: run.sequences.map(toTrace),
  };
}

// The server reads index_range as a closed range. The models send an exclusive end (they add 1
// to the last index they show), so the end moves back by one. Empty values are left out, except
// q, which is always sent.
export function toExplorerSequenceQuery(params: { [key: string]: unknown }): {
  [key: string]: unknown;
} {
  const query: { [key: string]: unknown } = { q: params.q ?? '' };
  for (const [key, value] of Object.entries(params)) {
    if (key === 'q' || value === '' || value === null || value === undefined) {
      continue;
    }
    query[key] = value;
  }
  if (typeof query.index_range === 'string') {
    const [low, high] = query.index_range.split(':').map(Number);
    query.index_range = `${low}:${Math.max(low, high - 1)}`;
  }
  return query;
}
