import { ITagProps } from 'types/pages/tags/Tags';
import {
  IMetricTrace,
  IRun,
  ISequence,
  ITraceData,
} from 'types/services/models/metrics/runModel';

// The explorer API (/api/v1/explorer) answers with JSON. The UI models read traces as typed
// arrays, so this module converts the JSON once, at the edge: each point list becomes float64
// buffers in the shape the models already use.

// [step, value, epoch, timestamp]; epoch and timestamp are null for points without them.
export type ExplorerPoint = [number, number, number | null, number | null];

export interface IExplorerTrace {
  name: string;
  context: { [key: string]: unknown };
  count: number;
  last: number | null;
  points: ExplorerPoint[];
}

export interface IExplorerRunProps {
  name: string;
  description: string;
  archived: boolean;
  status: string;
  active: boolean;
  project: string;
  experiment: { id: string | null; name: string; description: string };
  creator: { username: string | null } | null;
  creation_time: number;
  end_time: number | null;
  tags: { id: string; name: string; color: string | null }[];
}

export interface IExplorerRun {
  props: IExplorerRunProps;
  params: { [key: string]: any };
  traces: IExplorerTrace[];
}

export interface IExplorerSearch {
  runs: { [runId: string]: IExplorerRun };
  progress: [number, number];
}

export function float64Buffer(values: number[]): ITraceData {
  const array = new Float64Array(values);
  return {
    blob: new Uint8Array(array.buffer),
    dtype: 'float64',
    shape: values.length,
    type: 'float64',
  };
}

function aggregates(values: number[]) {
  if (!values.length) {
    return { min: null, max: null, first: null, last: null };
  }
  return {
    min: Math.min(...values),
    max: Math.max(...values),
    first: values[0],
    last: values[values.length - 1],
  };
}

export function toMetricTrace(trace: IExplorerTrace): IMetricTrace {
  const points = trace.points;
  return {
    name: trace.name,
    description: '',
    context: trace.context,
    slice: [0, points.length, 1],
    // The series buffers for the charts, plus the aggregates the run tables read.
    values: {
      ...float64Buffer(points.map((p) => p[1])),
      ...aggregates(points.map((p) => p[1])),
    } as ITraceData,
    iters: float64Buffer(points.map((p) => p[0])),
    epochs: float64Buffer(points.map((p) => p[2] ?? NaN)),
    timestamps: float64Buffer(points.map((p) => p[3] ?? NaN)),
    x_axis_values: null,
    x_axis_iters: null,
  };
}

function toTag(tag: IExplorerRunProps['tags'][number]): ITagProps {
  return {
    id: tag.id,
    name: tag.name,
    color: tag.color,
    description: '',
    run_count: 0,
    archived: false,
  };
}

// The display fields of a run, in the shape the run tables and detail pages read.
export function toRunProps(
  props: IExplorerRunProps,
): IRun<IMetricTrace>['props'] {
  return {
    experiment: {
      id: props.experiment.id ?? '',
      name: props.experiment.name,
      description: props.experiment.description,
    },
    creator: props.creator?.username
      ? { username: props.creator.username, email: '', photo: null }
      : null,
    name: props.name,
    creation_time: props.creation_time,
    end_time: props.end_time ?? 0,
    description: props.description,
    active: props.active,
    tags: props.tags.map(toTag),
  };
}

export function toRun(hash: string, run: IExplorerRun): IRun<IMetricTrace> {
  return {
    hash,
    params: run.params,
    created_at: run.props.creation_time,
    props: toRunProps(run.props),
    traces: { metric: run.traces.map(toMetricTrace) },
  };
}

// Yields the same [keys, value] items the old stream decoder produced: one progress record,
// then one record per run, keyed by the run id.
// The metric explorer reads a run as a sequence: its traces are a flat list, not `traces.metric`.
export function toSequence(
  runId: string,
  run: IExplorerRun,
): ISequence<IMetricTrace> {
  const shaped = toRun(runId, run);
  return {
    hash: runId,
    params: shaped.params,
    props: shaped.props,
    created_at: shaped.created_at,
    traces: run.traces.map(toMetricTrace),
  } as unknown as ISequence<IMetricTrace>;
}

export async function* iterExplorerRuns(
  search: IExplorerSearch,
  shape: (runId: string, run: IExplorerRun) => unknown = toRun,
): AsyncGenerator<[string[], any]> {
  yield [['progress'], search.progress];
  for (const [runId, run] of Object.entries(search.runs)) {
    yield [[runId], shape(runId, run)];
  }
}

// The traces of one run in a search response, as metric traces (run detail reads these).
export function runTraces(
  search: IExplorerSearch,
  runId: string,
): IMetricTrace[] {
  return (search.runs[runId]?.traces ?? []).map(toMetricTrace);
}

// The log chunks of a run ({stream, seq, lines: [{ts, text}]}) as one record per line, in time
// order. The log view reads each record as {index, value: text}.
export interface IExplorerLogChunk {
  stream: string;
  seq: number;
  lines: { ts: number; text: string }[];
}

export interface IExplorerLogLine {
  ts: number;
  text: string;
  stream: string;
}

// Every line of the run's log chunks, oldest first.
export function sortedLogLines(
  chunks: IExplorerLogChunk[],
): IExplorerLogLine[] {
  return chunks
    .flatMap((chunk) =>
      chunk.lines.map((line) => ({
        ts: line.ts,
        text: line.text,
        stream: chunk.stream,
      })),
    )
    .sort((a, b) => a.ts - b.ts);
}

export function logRecords(chunks: IExplorerLogChunk[]): {
  [index: string]: { index: number; value: string };
} {
  const records: { [index: string]: { index: number; value: string } } = {};
  sortedLogLines(chunks).forEach((line, index) => {
    records[index] = { index, value: line.text };
  });
  return records;
}

// Every run of a search response, as run objects (the dashboard and experiment lists read these).
export function runsList(search: IExplorerSearch): IRun<IMetricTrace>[] {
  return Object.entries(search.runs).map(([runId, run]) => toRun(runId, run));
}
