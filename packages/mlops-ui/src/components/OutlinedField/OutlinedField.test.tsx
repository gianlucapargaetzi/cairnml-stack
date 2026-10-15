import React from 'react';

import { MenuItem } from '@material-ui/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import OutlinedField from './OutlinedField';

describe('<OutlinedField /> numeric box', () => {
  function renderNumeric(onChange = jest.fn()) {
    render(
      <OutlinedField
        id='cpu'
        label='CPU'
        numeric
        value=''
        onChange={onChange}
      />,
    );
    return { input: screen.getByRole('textbox'), onChange };
  }

  test('accepts digits and one decimal point', () => {
    const { input, onChange } = renderNumeric();

    fireEvent.change(input, { target: { value: '1.5' } });

    expect(onChange).toHaveBeenCalledTimes(1);
  });

  test('refuses a second decimal point', () => {
    const { input, onChange } = renderNumeric();

    fireEvent.change(input, { target: { value: '1.2.3' } });

    expect(onChange).not.toHaveBeenCalled();
  });

  test('refuses pasted text that is not a number', () => {
    const { input, onChange } = renderNumeric();

    fireEvent.change(input, { target: { value: 'abc' } });
    fireEvent.change(input, { target: { value: '-4' } });

    expect(onChange).not.toHaveBeenCalled();
  });

  test('blocks typed letters and signs but not digits', () => {
    const { input } = renderNumeric();

    // fireEvent returns false when the handler prevented the default action.
    expect(fireEvent.keyDown(input, { key: 'a' })).toBe(false);
    expect(fireEvent.keyDown(input, { key: 'e' })).toBe(false);
    expect(fireEvent.keyDown(input, { key: '-' })).toBe(false);
    expect(fireEvent.keyDown(input, { key: '+' })).toBe(false);
    expect(fireEvent.keyDown(input, { key: '7' })).toBe(true);
    expect(fireEvent.keyDown(input, { key: '.' })).toBe(true);
  });

  test('keeps keyboard shortcuts such as copy and paste', () => {
    const { input } = renderNumeric();

    expect(fireEvent.keyDown(input, { key: 'v', ctrlKey: true })).toBe(true);
    expect(fireEvent.keyDown(input, { key: 'c', metaKey: true })).toBe(true);
  });

  test('a text box accepts any text', () => {
    const onChange = jest.fn();
    render(
      <OutlinedField id='name' label='Name' value='' onChange={onChange} />,
    );

    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'abc-1' },
    });

    expect(onChange).toHaveBeenCalledTimes(1);
  });
});

describe('<OutlinedField /> dropdown menu', () => {
  function Dropdown({ initial = '' }: { initial?: string }) {
    const [value, setValue] = React.useState(initial);
    return (
      <OutlinedField
        id='direction'
        label='Better is'
        select
        value={value}
        onValueChange={setValue}
      >
        <MenuItem value='min'>min</MenuItem>
        <MenuItem value='max'>max</MenuItem>
      </OutlinedField>
    );
  }

  function labelElement() {
    return document.querySelector('label[for="direction"]') as HTMLElement;
  }

  function openMenu() {
    fireEvent.mouseDown(screen.getByRole('button'));
  }

  function closeMenuWithoutChoosing() {
    fireEvent.keyDown(screen.getByRole('listbox'), { key: 'Escape' });
  }

  test('the label sits in the box while nothing is chosen', () => {
    render(<Dropdown />);

    expect(labelElement()).not.toHaveClass('MuiInputLabel-shrink');
  });

  test('the label moves up while the menu is open', () => {
    render(<Dropdown />);

    openMenu();

    expect(labelElement()).toHaveClass('MuiInputLabel-shrink');
  });

  test('closing the menu without a choice puts the label back in the box', async () => {
    render(<Dropdown />);
    openMenu();

    closeMenuWithoutChoosing();

    await waitFor(() =>
      expect(labelElement()).not.toHaveClass('MuiInputLabel-shrink'),
    );
  });

  test('choosing a value keeps the label up after the menu closes', async () => {
    render(<Dropdown />);
    openMenu();

    fireEvent.click(screen.getByRole('option', { name: 'max' }));

    await waitFor(() =>
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument(),
    );
    expect(labelElement()).toHaveClass('MuiInputLabel-shrink');
    expect(screen.getByRole('button')).toHaveTextContent('max');
  });

  test('the box is not left focused once the menu has closed', async () => {
    render(<Dropdown />);
    openMenu();

    closeMenuWithoutChoosing();

    await waitFor(() => expect(screen.getByRole('button')).not.toHaveFocus());
  });
});

describe('<OutlinedField /> outline notch', () => {
  // MUI draws the notch in a <legend> with a `legendNotched` class while the label is up.
  function notchIsOpen(container: HTMLElement) {
    const legend = container.querySelector('legend') as HTMLElement;
    return /legendNotched/.test(legend.className);
  }

  test('a text box moves its notch with its label on focus and blur', () => {
    const { container } = render(
      <OutlinedField id='name' label='Name' value='' />,
    );
    const input = screen.getByRole('textbox');

    expect(notchIsOpen(container)).toBe(false);
    fireEvent.focus(input);
    expect(notchIsOpen(container)).toBe(true);
    fireEvent.blur(input);
    expect(notchIsOpen(container)).toBe(false);
  });

  test('a dropdown moves its notch with its label while the menu is open', async () => {
    function Dropdown() {
      const [value, setValue] = React.useState('');
      return (
        <OutlinedField
          id='direction'
          label='Better is'
          select
          value={value}
          onValueChange={setValue}
        >
          <MenuItem value='min'>min</MenuItem>
          <MenuItem value='max'>max</MenuItem>
        </OutlinedField>
      );
    }
    const { container } = render(<Dropdown />);
    const label = document.querySelector(
      'label[for="direction"]',
    ) as HTMLElement;

    fireEvent.mouseDown(screen.getByRole('button'));
    expect(notchIsOpen(container)).toBe(true);
    expect(label).toHaveClass('MuiInputLabel-shrink');

    // Straight after closing, before the menu has finished leaving, the notch and the label must
    // already agree: the label is down, so the notch is down too.
    fireEvent.keyDown(screen.getByRole('listbox'), { key: 'Escape' });
    expect(label).not.toHaveClass('MuiInputLabel-shrink');
    expect(notchIsOpen(container)).toBe(false);
    await waitFor(() => expect(notchIsOpen(container)).toBe(false));
  });
});
