import {
  sequenceTraceEntries,
  toExplorerTraceQuery,
  IExplorerSequenceSearch,
  toExplorerSequenceQuery,
  toSequenceRun,
} from './sequenceJson';

const search: IExplorerSequenceSearch = {
  runs: {
    run_1: {
      props: {
        name: 'fast',
        description: '',
        archived: false,
        status: 'finished',
        active: false,
        project: 'vision/seg',
        experiment: { id: 'exp_1', name: 'training', description: '' },
        creator: { username: 'alice' },
        creation_time: 100,
        end_time: 160,
        tags: [],
      },
      params: { lr: 0.1 },
      ranges: {
        record_range_total: [0, 3],
        index_range_total: [0, 2],
        record_range_used: [0, 3],
        index_range_used: [0, 2],
      },
      sequences: [
        {
          name: 'pred',
          context: { subset: 'val' },
          count: 3,
          items: [
            {
              step: 0,
              idx: 0,
              epoch: null,
              ts: 1,
              caption: 'a',
              format: 'png',
              width: 8,
              height: 4,
              blob_uri: 'https://nas/0_0.png',
            },
            {
              step: 0,
              idx: 1,
              epoch: null,
              ts: 1,
              caption: 'b',
              format: 'png',
              width: 8,
              height: 4,
              blob_uri: 'https://nas/0_1.png',
            },
            {
              step: 2,
              idx: 0,
              epoch: null,
              ts: 2,
              caption: 'c',
              format: 'png',
              width: 8,
              height: 4,
              blob_uri: 'https://nas/2_0.png',
            },
          ],
        },
      ],
    },
  },
  progress: [1, 1],
};

describe('toSequenceRun', () => {
  it('shapes a run the images model reads: props, params and one trace per sequence', () => {
    const run = toSequenceRun('run_1', search.runs.run_1, 'image');

    expect(run.hash).toBe('run_1');
    expect(run.params).toEqual({ lr: 0.1 });
    expect(run.ranges.record_range_total).toEqual([0, 3]);
    expect(run.props.name).toBe('fast');
    expect(run.props.experiment).toEqual({
      id: 'exp_1',
      name: 'training',
      description: '',
    });
    expect(run.traces).toHaveLength(1);
    const [trace] = run.traces;
    expect(trace.name).toBe('pred');
    expect(trace.context).toEqual({ subset: 'val' });
    expect(trace.iters).toEqual([0, 2]);
  });

  it('groups the items of each sampled step, with the fields the image boxes read', () => {
    const [trace] = toSequenceRun('run_1', search.runs.run_1, 'image').traces;

    expect(trace.values).toHaveLength(2);
    expect(trace.values[0]).toEqual([
      {
        blob_uri: 'https://nas/0_0.png',
        caption: 'a',
        format: 'png',
        width: 8,
        height: 4,
        index: 0,
      },
      {
        blob_uri: 'https://nas/0_1.png',
        caption: 'b',
        format: 'png',
        width: 8,
        height: 4,
        index: 1,
      },
    ]);
    expect(trace.values[1][0].blob_uri).toBe('https://nas/2_0.png');
  });

  it('keeps text values inline and gives them the text field', () => {
    const texts: IExplorerSequenceSearch = {
      runs: {
        run_2: {
          ...search.runs.run_1,
          sequences: [
            {
              name: 'log',
              context: {},
              count: 1,
              items: [
                {
                  step: 0,
                  idx: 0,
                  epoch: null,
                  ts: 1,
                  caption: null,
                  format: null,
                  width: null,
                  height: null,
                  text: 'epoch 0',
                },
              ],
            },
          ],
        },
      },
      progress: [1, 1],
    };
    const [trace] = toSequenceRun('run_2', texts.runs.run_2, 'text').traces;
    expect(trace.values[0][0]).toMatchObject({ text: 'epoch 0' });
    expect(trace.values[0][0]).not.toHaveProperty('blob_uri');
  });
});

describe('toExplorerSequenceQuery', () => {
  it("turns the model's exclusive index end into the closed range the server reads", () => {
    // The model asks for indices 0 to 4 inclusive as "0:5".
    const query = toExplorerSequenceQuery({
      q: "images.name == 'pred'",
      index_range: '0:5',
      record_range: '2:10',
      record_density: 20,
      index_density: 3,
    });
    expect(query).toEqual({
      q: "images.name == 'pred'",
      index_range: '0:4',
      record_range: '2:10',
      record_density: 20,
      index_density: 3,
    });
  });

  it('drops empty ranges and densities', () => {
    expect(
      toExplorerSequenceQuery({ q: '', index_range: '', record_density: '' }),
    ).toEqual({
      q: '',
    });
  });
});

describe('sequenceTraceEntries', () => {
  const target = { name: 'pred', context: { subset: 'val' } };
  const run = {
    ...search.runs.run_1,
    sequences: [
      {
        name: 'pred',
        context: {},
        count: 1,
        items: [
          {
            step: 9,
            idx: 0,
            epoch: null,
            ts: 1,
            caption: 'other',
            format: 'png',
            width: 1,
            height: 1,
            blob_uri: 'https://nas/x',
          },
        ],
      },
      {
        name: 'pred',
        context: { subset: 'val' },
        count: 2,
        items: [
          {
            step: 4,
            idx: 0,
            epoch: null,
            ts: 1,
            caption: 'v',
            format: 'png',
            width: 8,
            height: 4,
            blob_uri: 'https://nas/v40',
          },
          {
            step: 5,
            idx: 0,
            epoch: null,
            ts: 1,
            caption: 'v',
            format: 'png',
            width: 8,
            height: 4,
            blob_uri: 'https://nas/v50',
          },
        ],
      },
    ],
    ranges: {
      record_range_total: [4, 6],
      index_range_total: [0, 1],
      record_range_used: [4, 6],
      index_range_used: [0, 1],
    },
  };
  const searchOfRun = {
    runs: { run_1: run },
    progress: [1, 1] as [number, number],
  };

  it('gives the model one value per field, for the sequence with the same name and context', () => {
    const entries = Object.fromEntries(
      sequenceTraceEntries(searchOfRun, target),
    );
    expect(entries.name).toBe('pred');
    expect(entries.context).toEqual({ subset: 'val' });
    expect(entries.iters).toEqual([4, 5]);
    expect(entries.values[0][0].blob_uri).toBe('https://nas/v40');
    expect(entries.record_range_total).toEqual([4, 6]);
    expect(entries.index_range_total).toEqual([0, 1]);
  });

  it('gives an empty trace when the run has no sequence of that name and context', () => {
    const entries = Object.fromEntries(
      sequenceTraceEntries(searchOfRun, { name: 'missing', context: {} }),
    );
    expect(entries.iters).toEqual([]);
    expect(entries.values).toEqual([]);
  });
});

describe('toExplorerTraceQuery', () => {
  it('closes both ranges, since the run detail page sends exclusive ends for both', () => {
    expect(
      toExplorerTraceQuery({ q: 'x', record_range: '2:5', index_range: '0:3' }),
    ).toEqual({
      q: 'x',
      record_range: '2:4',
      index_range: '0:2',
    });
  });
});
