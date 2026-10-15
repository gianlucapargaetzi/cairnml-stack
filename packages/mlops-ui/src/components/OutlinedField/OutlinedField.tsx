import React from 'react';
import classNames from 'classnames';

import { TextField } from '@material-ui/core';
import { OutlinedTextFieldProps } from '@material-ui/core/TextField';

import './OutlinedField.scss';

export interface IOutlinedFieldProps
  extends Omit<
    OutlinedTextFieldProps,
    | 'variant'
    | 'label'
    | 'id'
    | 'value'
    | 'onChange'
    | 'onKeyDown'
    | 'multiline'
    | 'select'
    | 'ref'
  > {
  id: string;
  label: string;
  value?: string | number;
  // Shown at the end of the box, for example the search icon of the search box.
  endAdornment?: React.ReactNode;
  // A text box. Pass `numeric` for a number box: digits and one decimal point only.
  numeric?: boolean;
  multiline?: boolean;
  onChange?: (
    event: React.ChangeEvent<HTMLTextAreaElement | HTMLInputElement>,
  ) => void;
  onKeyDown?: (
    event: React.KeyboardEvent<HTMLTextAreaElement | HTMLInputElement>,
  ) => void;
  // A dropdown. Pass MenuItem children; `onValueChange` receives the chosen value.
  select?: boolean;
  onValueChange?: (value: string) => void;
  children?: React.ReactNode;
}

const NUMBER_PATTERN = /^\d*\.?\d*$/;

// The list opens below the box, not over it (MUI otherwise lines the chosen item up with the box).
const MENU_BELOW_BOX = {
  getContentAnchorEl: null,
  anchorOrigin: { vertical: 'bottom', horizontal: 'left' },
  transformOrigin: { vertical: 'top', horizontal: 'left' },
} as const;

// One text, number or dropdown box, built on MUI's TextField exactly as the reference search box
// is: the label and the outline's notch share one `shrink` value, so they move together. A text box
// moves its label on focus and value. A dropdown moves its label while its menu is open or a value
// is chosen.
function OutlinedField({
  id,
  label,
  className,
  value,
  select = false,
  numeric = false,
  multiline = false,
  onChange,
  onKeyDown,
  onValueChange,
  children,
  endAdornment,
  disabled,
  error,
  ...rest
}: IOutlinedFieldProps) {
  const [isMenuOpen, setIsMenuOpen] = React.useState(false);
  const hasValue = value !== undefined && value !== null && value !== '';
  // Undefined for text boxes: MUI then moves the label and the notch on focus and value.
  const shrink = select ? isMenuOpen || hasValue : undefined;

  // MUI hands focus back to the box as soon as the menu closes, so the box stays focused and keeps
  // its focused border and label colour. A text box loses focus on blur; give the dropdown the same
  // idle state the moment its menu closes.
  const wasMenuOpen = React.useRef(false);
  React.useEffect(() => {
    if (isMenuOpen) {
      wasMenuOpen.current = true;
      return;
    }
    if (!wasMenuOpen.current) {
      return;
    }
    wasMenuOpen.current = false;
    const box = document.getElementById(id);
    if (box && document.activeElement === box) {
      box.blur();
    }
  }, [isMenuOpen, id]);

  const handleKeyDown = (
    event: React.KeyboardEvent<HTMLTextAreaElement | HTMLInputElement>,
  ) => {
    const isCharacter = event.key.length === 1;
    const isShortcut = event.ctrlKey || event.metaKey;
    if (numeric && isCharacter && !isShortcut && !/[\d.]/.test(event.key)) {
      event.preventDefault();
    }
    onKeyDown?.(event);
  };

  const handleChange = (
    event: React.ChangeEvent<HTMLTextAreaElement | HTMLInputElement>,
  ) => {
    if (numeric && !NUMBER_PATTERN.test(event.target.value)) {
      return;
    }
    onChange?.(event);
  };

  return (
    <TextField
      {...rest}
      id={id}
      label={label}
      className={classNames(
        'OutlinedField',
        { OutlinedField_multiline: multiline },
        className,
      )}
      variant='outlined'
      fullWidth
      select={select}
      value={value ?? (select ? '' : undefined)}
      disabled={disabled}
      error={error}
      multiline={multiline}
      autoComplete='off'
      InputLabelProps={{ shrink, color: 'primary' }}
      InputProps={{ endAdornment }}
      inputProps={
        select
          ? undefined
          : {
              onKeyDown: handleKeyDown,
              ...(numeric ? { inputMode: 'decimal' } : {}),
            }
      }
      onChange={
        select
          ? (event) => onValueChange?.(String(event.target.value))
          : handleChange
      }
      SelectProps={
        select
          ? {
              onOpen: () => setIsMenuOpen(true),
              onClose: () => setIsMenuOpen(false),
              MenuProps: {
                ...MENU_BELOW_BOX,
              },
            }
          : undefined
      }
    >
      {children}
    </TextField>
  );
}

OutlinedField.displayName = 'OutlinedField';

export default React.memo(OutlinedField);
