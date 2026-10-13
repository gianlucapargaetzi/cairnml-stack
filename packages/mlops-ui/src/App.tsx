import React from 'react';
import { BrowserRouter, Switch, Route, Redirect } from 'react-router-dom';
import { useModel } from 'hooks';

import { loader } from '@monaco-editor/react';

import AlertBanner from 'components/kit/AlertBanner';
import SideBar from 'components/SideBar/SideBar';
import ProjectWrapper from 'components/ProjectWrapper/ProjectWrapper';
import Theme from 'components/Theme/Theme';
import BusyLoaderWrapper from 'components/BusyLoaderWrapper/BusyLoaderWrapper';
import ErrorBoundary from 'components/ErrorBoundary/ErrorBoundary';

import PageWrapper from 'pages/PageWrapper';

import routes from 'routes/routes';

import projectsModel from 'services/models/projects/projectsModel';
import { loadSession } from 'services/session/session';

import { IProjectsModelState } from './types/services/models/projects/projectsModel';

import './App.scss';

// The router lives under the fork's public path (/ui-next), set by homepage in package.json.
const basePath = process.env.PUBLIC_URL ?? '';

// loading monaco from node modules instead of CDN
loader.config({
  paths: {
    vs: `${process.env.PUBLIC_URL}/vs`,
  },
});

function App(): React.FunctionComponentElement<React.ReactNode> {
  const projectsData = useModel<Partial<IProjectsModelState>>(projectsModel);
  const [sessionReady, setSessionReady] = React.useState(false);

  React.useEffect(() => {
    // Nothing loads until the server confirms the session and hands over the CSRF token.
    loadSession().then(() => setSessionReady(true));
  }, []);

  React.useEffect(() => {
    if (!sessionReady) {
      return;
    }
    let timeoutId: number;
    const preloader = document.getElementById('preload-spinner');
    if (preloader) {
      preloader.classList.add('preloader-fade-out');
      timeoutId = window.setTimeout(() => {
        preloader.remove();
      }, 500);
    }

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [sessionReady]);

  if (!sessionReady) {
    return <BusyLoaderWrapper height='100vh' isLoading />;
  }

  return (
    <BrowserRouter basename={basePath}>
      <ProjectWrapper />
      <Theme>
        {projectsData?.project?.warn_index && (
          <AlertBanner type='warning'>
            Index db was corrupted and deleted. Please run
            <b>`aim storage reindex`</b> command to restore optimal performance.
          </AlertBanner>
        )}
        {projectsData?.project?.warn_runs && (
          <AlertBanner type='warning'>
            Corrupted runs were detected. Please run
            <b>`aim runs rm --corrupted`</b> command to remove corrupted runs.
          </AlertBanner>
        )}
        <div className='pageContainer'>
          <ErrorBoundary>
            <SideBar />
          </ErrorBoundary>
          <div className='mainContainer'>
            <React.Suspense
              fallback={<BusyLoaderWrapper height='100vh' isLoading />}
            >
              <Switch>
                {Object.values(routes).map((route, index) => {
                  const { component: Component, path, isExact, title } = route;
                  return (
                    <Route path={path} key={index} exact={isExact}>
                      <ErrorBoundary>
                        <PageWrapper path={path} title={title}>
                          <Component />
                        </PageWrapper>
                      </ErrorBoundary>
                    </Route>
                  );
                })}
                <Redirect to='/' />
              </Switch>
            </React.Suspense>
          </div>
        </div>
      </Theme>
    </BrowserRouter>
  );
}

export default App;
