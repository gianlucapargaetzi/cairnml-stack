import React from 'react';

import { PathEnum } from 'config/enums/routesEnum';
import pageTitlesEnum from 'config/pageTitles/pageTitles';

const Runs = React.lazy(
  () => import(/* webpackChunkName: "runs" */ 'pages/Runs/RunsContainer'),
);
const RunDetail = React.lazy(
  () => import(/* webpackChunkName: "run" */ 'pages/RunDetail/RunDetail'),
);
const Metrics = React.lazy(
  () =>
    import(/* webpackChunkName: "metrics" */ 'pages/Metrics/MetricsContainer'),
);
const Params = React.lazy(
  () => import(/* webpackChunkName: "params" */ 'pages/Params/ParamsContainer'),
);
const Dashboard = React.lazy(
  () => import(/* webpackChunkName: "dashboard" */ 'pages/Dashboard/Dashboard'),
);
const Compare = React.lazy(
  () => import(/* webpackChunkName: "compare" */ 'pages/Compare/Compare'),
);
const ExperimentPage = React.lazy(
  () =>
    import(/* webpackChunkName: "experiment" */ 'pages/Experiment/Experiment'),
);
const Tags = React.lazy(
  () => import(/* webpackChunkName: "tags" */ 'pages/Tags/Tags'),
);
const Projects = React.lazy(
  () => import(/* webpackChunkName: "projects" */ 'pages/Projects/Projects'),
);
const Datasets = React.lazy(
  () => import(/* webpackChunkName: "datasets" */ 'pages/Datasets/Datasets'),
);
const Admin = React.lazy(
  () => import(/* webpackChunkName: "admin" */ 'pages/Admin/Admin'),
);
const Account = React.lazy(
  () => import(/* webpackChunkName: "account" */ 'pages/Account/Account'),
);
const Resources = React.lazy(
  () => import(/* webpackChunkName: "resources" */ 'pages/Resources/Resources'),
);
const Jobs = React.lazy(
  () => import(/* webpackChunkName: "jobs" */ 'pages/Jobs/Jobs'),
);
const ImagesExplore = React.lazy(
  () =>
    import(
      /* webpackChunkName: "images" */ 'pages/ImagesExplore/ImagesExplore'
    ),
);
const Scatters = React.lazy(
  () =>
    import(
      /* webpackChunkName: "scatters" */ 'pages/Scatters/ScattersContainer'
    ),
);
export interface IRoute {
  path: PathEnum;
  component:
    | React.LazyExoticComponent<
        () => React.FunctionComponentElement<React.ReactNode>
      >
    | any;
  showInSidebar: boolean;
  displayName: string | null;
  icon?: string | null;
}

const routes: { [key: string]: any } = {
  DASHBOARD: {
    path: PathEnum.Dashboard,
    component: Dashboard,
    showInSidebar: false,
    displayName: 'Dashboard',
    icon: 'dashboard',
    isExact: true,
    title: pageTitlesEnum.DASHBOARD,
  },
  RUNS: {
    path: PathEnum.Runs,
    component: Runs,
    showInSidebar: true,
    displayName: 'Runs',
    icon: 'runs',
    isExact: true,
    title: pageTitlesEnum.RUNS_EXPLORER,
  },
  METRICS: {
    path: PathEnum.Metrics,
    component: Metrics,
    showInSidebar: true,
    displayName: 'Metrics',
    icon: 'metrics',
    isExact: true,
    title: pageTitlesEnum.METRICS_EXPLORER,
  },
  PARAMS: {
    path: PathEnum.Params,
    component: Params,
    showInSidebar: true,
    displayName: 'Params',
    icon: 'params',
    isExact: true,
    title: pageTitlesEnum.PARAMS_EXPLORER,
  },
  SCATTERS: {
    path: PathEnum.Scatters,
    component: Scatters,
    showInSidebar: true,
    displayName: 'Scatters',
    icon: 'scatterplot',
    isExact: true,
    title: pageTitlesEnum.SCATTERS_EXPLORER,
  },
  COMPARE: {
    path: PathEnum.Compare,
    component: Compare,
    showInSidebar: false,
    displayName: 'Compare',
    icon: 'runs',
    isExact: true,
    title: pageTitlesEnum.COMPARE,
  },
  EXPERIMENT: {
    path: PathEnum.Experiment_Page,
    component: ExperimentPage,
    showInSidebar: false,
    displayName: 'Experiment',
    icon: 'runs',
    isExact: true,
    title: pageTitlesEnum.EXPERIMENT,
  },
  TAGS: {
    path: PathEnum.Tags,
    component: Tags,
    showInSidebar: true,
    displayName: 'Tags',
    icon: 'tags',
    isExact: true,
    title: pageTitlesEnum.TAGS,
  },
  PROJECTS: {
    path: PathEnum.Projects,
    component: Projects,
    showInSidebar: true,
    displayName: 'Projects',
    icon: 'runs',
    isExact: true,
    title: pageTitlesEnum.PROJECTS,
  },
  DATASETS: {
    path: PathEnum.Datasets,
    component: Datasets,
    showInSidebar: true,
    displayName: 'Datasets',
    icon: 'runs',
    isExact: true,
    title: pageTitlesEnum.DATASETS,
  },
  ADMIN: {
    path: PathEnum.Admin,
    component: Admin,
    showInSidebar: true,
    displayName: 'Admin',
    icon: 'params',
    isExact: true,
    title: pageTitlesEnum.ADMIN,
  },
  ACCOUNT: {
    path: PathEnum.Account,
    component: Account,
    showInSidebar: false,
    displayName: 'Account',
    icon: 'params',
    isExact: true,
    title: pageTitlesEnum.ACCOUNT,
  },
  RESOURCES: {
    path: PathEnum.Resources,
    component: Resources,
    showInSidebar: true,
    displayName: 'Resources',
    icon: 'metrics',
    isExact: true,
    title: pageTitlesEnum.RESOURCES,
  },
  JOBS: {
    path: PathEnum.Jobs,
    component: Jobs,
    showInSidebar: true,
    displayName: 'Jobs',
    icon: 'runs',
    isExact: true,
    title: pageTitlesEnum.JOBS,
  },
  IMAGES: {
    path: PathEnum.Images_Explore,
    component: ImagesExplore,
    showInSidebar: true,
    displayName: 'Images',
    icon: 'images',
    isExact: true,
    title: pageTitlesEnum.IMAGES_EXPLORER,
  },
  RUN_DETAIL: {
    path: PathEnum.Run_Detail,
    component: RunDetail,
    showInSidebar: false,
    displayName: 'Run Detail',
    isExact: false,
    title: pageTitlesEnum.RUN_DETAIL,
  },
};

export default routes;
