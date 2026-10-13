import {
  datasetLink,
  filterDatasets,
  formatBytes,
  IDatasetRow,
} from './datasets';

const rows: IDatasetRow[] = [
  {
    project: 'vision/seg',
    repo: 'lab/data',
    ref: 'main',
    path: 'train.dvc',
    title: 'Train split',
    type: 'images',
    license: 'CC-BY',
    size_bytes: 2_500_000,
    nfiles: 3,
    has_card: true,
  },
  {
    project: 'vision/seg',
    repo: 'lab/data',
    ref: 'main',
    path: 'val.dvc',
    title: null,
    type: 'tabular',
    license: null,
    size_bytes: null,
    nfiles: null,
    has_card: false,
  },
  {
    project: 'secret/lab',
    repo: 'lab/other',
    ref: 'main',
    path: 'raw/x.dvc',
    title: 'Raw',
    type: 'images',
    license: null,
    size_bytes: 10,
    nfiles: 1,
    has_card: false,
  },
];

describe('formatBytes', () => {
  it('uses the largest unit with one decimal, and a dash when unknown', () => {
    expect(formatBytes(999)).toBe('999 B');
    expect(formatBytes(2_500)).toBe('2.5 kB');
    expect(formatBytes(2_500_000)).toBe('2.5 MB');
    expect(formatBytes(3_000_000_000)).toBe('3.0 GB');
    expect(formatBytes(null)).toBe('–');
  });
});

describe('filterDatasets', () => {
  it('filters by project, type and a search over path and title', () => {
    expect(
      filterDatasets(rows, { project: 'vision/seg', type: '', query: '' }),
    ).toHaveLength(2);
    expect(
      filterDatasets(rows, { project: '', type: 'images', query: '' }),
    ).toHaveLength(2);
    expect(
      filterDatasets(rows, { project: '', type: '', query: 'train' }),
    ).toHaveLength(1);
    expect(
      filterDatasets(rows, {
        project: 'vision/seg',
        type: 'images',
        query: '',
      }),
    ).toHaveLength(1);
  });
});

describe('datasetLink', () => {
  it('links to the detail view with project, repo and path in the query', () => {
    expect(datasetLink(rows[0])).toBe(
      '/datasets?project=vision%2Fseg&repo=lab%2Fdata&path=train.dvc',
    );
  });
});
