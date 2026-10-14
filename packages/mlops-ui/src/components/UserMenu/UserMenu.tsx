import React from 'react';
import { useHistory } from 'react-router-dom';
import Avatar from 'react-avatar';

import { Button, Text } from 'components/kit';
import ControlPopover from 'components/ControlPopover/ControlPopover';
import ErrorBoundary from 'components/ErrorBoundary/ErrorBoundary';

import { PathEnum } from 'config/enums/routesEnum';

import { getSession, signOut } from 'services/session/session';

import stringToColor from 'utils/stringToColor';

import './UserMenu.scss';

// The signed-in user, as a round avatar. Clicking it opens the account widget.
function UserMenu(): React.FunctionComponentElement<React.ReactNode> | null {
  const history = useHistory();
  const session = getSession();
  const [signOutError, setSignOutError] = React.useState<string | null>(null);

  if (!session) {
    return null;
  }
  const username = session.username ?? 'Account';

  function handleSignOut() {
    setSignOutError(null);
    signOut().catch((error) => setSignOutError(error.message));
  }

  return (
    <ErrorBoundary>
      <ControlPopover
        anchor={({ onAnchorClick }) => (
          <button
            type='button'
            className='UserMenu__avatar'
            aria-label='Account menu'
            onClick={onAnchorClick}
          >
            <Avatar
              name={username}
              color={stringToColor(username)}
              size='32'
              round={true}
              textSizeRatio={2}
              style={{ fontWeight: 600 }}
            />
          </button>
        )}
        anchorOrigin={{ vertical: 'top', horizontal: 'right' }}
        transformOrigin={{ vertical: 'bottom', horizontal: 'left' }}
        component={({ handleClose }) => (
          <div className='UserMenu__panel'>
            <Text size={12} tint={50}>
              Signed in as:
            </Text>
            <Text size={14} weight={600} tint={100} className='UserMenu__name'>
              {username}
            </Text>
            <div className='UserMenu__actions'>
              <Button
                variant='outlined'
                size='small'
                onClick={() => {
                  handleClose?.();
                  history.push(PathEnum.Settings);
                }}
              >
                Settings
              </Button>
              <Button variant='outlined' size='small' onClick={handleSignOut}>
                Sign out
              </Button>
            </div>
            {signOutError && (
              <Text size={12} color='error' className='UserMenu__error'>
                {signOutError}
              </Text>
            )}
          </div>
        )}
      />
    </ErrorBoundary>
  );
}

export default UserMenu;
