import React from 'react';
import classNames from 'classnames';

import ErrorBoundary from 'components/ErrorBoundary/ErrorBoundary';
import OutlinedField from 'components/OutlinedField/OutlinedField';

import { ISearchInputProps } from '../types';

import EndAdornment from './EndAdornment';

function SearchInput({
  value,
  onInputClear,
  onInputChange,
  isValidInput,
  isDisabled,
}: ISearchInputProps) {
  return (
    <ErrorBoundary>
      <OutlinedField
        className={classNames('SearchInput', { activeCloseButton: !!value })}
        id='search'
        label='Search'
        value={value}
        disabled={isDisabled}
        error={!isValidInput}
        onChange={(event) => onInputChange(event.target.value)}
        endAdornment={
          <EndAdornment
            isDisabled={isDisabled}
            showSearchIcon={!value}
            onClickClearButton={onInputClear}
          />
        }
      />
    </ErrorBoundary>
  );
}

export default React.memo<ISearchInputProps>(SearchInput);
