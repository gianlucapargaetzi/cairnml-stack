import React from 'react';

import ErrorBoundary from 'components/ErrorBoundary/ErrorBoundary';

import Text from '../Text';

import './Table.scss';

export interface ITableColumn {
  key: string;
  label: string;
}

export type ITableRow = Record<string, React.ReactNode>;

/**
 * Small read-only table with the house style. For large or sortable data use DataList.
 *
 * @property {ITableColumn[]} columns - column keys and header labels
 * @property {ITableRow[]} rows - one object per row, keyed by column key
 * @property {string} rowKey - name of the row field that identifies a row
 * @property {string} emptyText - shown instead of the table when there are no rows
 */
function Table({
  columns,
  rows,
  rowKey,
  emptyText,
}: {
  columns: ITableColumn[];
  rows: ITableRow[];
  rowKey: string;
  emptyText?: string;
}): React.FunctionComponentElement<React.ReactNode> | null {
  if (rows.length === 0) {
    return emptyText ? (
      <Text size={12} tint={50}>
        {emptyText}
      </Text>
    ) : null;
  }
  return (
    <ErrorBoundary>
      <div className='Table'>
        <table className='Table__table'>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column.key} className='Table__head'>
                  <Text size={12} weight={600} tint={60} component='span'>
                    {column.label}
                  </Text>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={String(row[rowKey])} className='Table__row'>
                {columns.map((column) => (
                  <td key={column.key} className='Table__cell'>
                    {typeof row[column.key] === 'string' ||
                    typeof row[column.key] === 'number' ? (
                      <Text size={12}>{row[column.key]}</Text>
                    ) : (
                      row[column.key]
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </ErrorBoundary>
  );
}

export default Table;
