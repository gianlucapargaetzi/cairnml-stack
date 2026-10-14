import React from 'react';

import ErrorBoundary from 'components/ErrorBoundary/ErrorBoundary';

import Text from '../Text';

import './DefinitionList.scss';

export interface IDefinitionItem {
  label: string;
  value: React.ReactNode;
  // Identifiers, ids and commands are shown in monospace.
  mono?: boolean;
}

/**
 * Read-only label and value pairs, two columns, labels in the table-label style.
 *
 * @property {IDefinitionItem[]} items - the pairs to show, in order
 */
function DefinitionList({
  items,
}: {
  items: IDefinitionItem[];
}): React.FunctionComponentElement<React.ReactNode> {
  return (
    <ErrorBoundary>
      <dl className='DefinitionList'>
        {items.map((item) => (
          <React.Fragment key={item.label}>
            <dt>
              <Text size={12} weight={600} tint={60}>
                {item.label}
              </Text>
            </dt>
            <dd>
              {typeof item.value === 'string' ||
              typeof item.value === 'number' ? (
                <Text
                  size={12}
                  component='span'
                  className={item.mono ? 'DefinitionList__mono' : undefined}
                >
                  {item.value}
                </Text>
              ) : (
                item.value
              )}
            </dd>
          </React.Fragment>
        ))}
      </dl>
    </ErrorBoundary>
  );
}

export default DefinitionList;
