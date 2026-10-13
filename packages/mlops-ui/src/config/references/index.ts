import { AIM_VERSION } from 'config/config';

const DOCUMENTATIONS = {
  MAIN_PAGE: '#',
  STABLE: '#',
  AIM_QL: '#',
  SUPPORTED_TYPES: '#',
  EXPLORERS: {
    SEARCH: '#',

    PARAMS: {
      MAIN: '#',
      SEARCH: '#',
    },
    METRICS: {
      MAIN: '#',
      SEARCH: '#',
    },
    IMAGES: {
      MAIN: '#',
      SEARCH: '#',
    },
    SCATTERS: {
      MAIN: '#',
      SEARCH: '#',
    },
    RUNS: {
      MAIN: '#',
      SEARCH: '#',
    },
  },
  INTEGRATIONS: {
    PYTORCH_LIGHTNING: '#',
    HUGGING_FACE: '#',
    KERAS: '#',
    KERAS_TUNER: '#',
    XGBOOST: '#',
    CATBOOST: '#',
    FASTAI: '#',
    LIGHT_GBM: '#',
    PYTORCH_IGNITE: '#',
  },
};

const DEMOS = {
  MAIN: '#',
};

const GUIDES = {
  SETUP: {
    COLAB_EXAMPLE: '#',
  },
};

/*
 getDocsVersion() returns the version of the docs to be used in the links
 */
function getDocsVersion() {
  let [majorVersion, minorVersion] = `${AIM_VERSION}`.split('.');
  return `v${majorVersion}.${minorVersion}.0`;
}

const version: string = getDocsVersion();

const DASHBOARD_PAGE_GUIDES: { name: string; url: string }[] = [
  {
    name: 'UI - Runs Management',
    url: `https://aimstack.readthedocs.io/en/${version}/ui/pages/run_management.html`,
  },
  {
    name: 'UI - Explorers',
    url: `https://aimstack.readthedocs.io/en/${version}/ui/pages/explorers.html`,
  },
  {
    name: 'UI - Bookmarks',
    url: `https://aimstack.readthedocs.io/en/${version}/ui/pages/bookmarks.html`,
  },
  {
    name: 'UI - Tags page',
    url: `https://aimstack.readthedocs.io/en/${version}/ui/pages/tags.html`,
  },
  {
    name: 'Manage runs',
    url: `https://aimstack.readthedocs.io/en/${version}/using/manage_runs.html`,
  },
  {
    name: 'Configure runs',
    url: `https://aimstack.readthedocs.io/en/${version}/using/configure_runs.html`,
  },
  {
    name: 'Query runs and objects',
    url: `https://aimstack.readthedocs.io/en/${version}/using/query_runs.html`,
  },
  {
    name: 'Query language basics',
    url: `https://aimstack.readthedocs.io/en/${version}/using/search.html`,
  },
  {
    name: 'Track experiments with aim remote server',
    url: `https://aimstack.readthedocs.io/en/${version}/using/remote_tracking.html`,
  },
  {
    name: 'Notify on failed/stuck runs',
    url: `https://aimstack.readthedocs.io/en/${version}/using/training_monitoring.html`,
  },
  {
    name: 'Log messages during training process',
    url: `https://aimstack.readthedocs.io/en/${version}/using/logging.html`,
  },
  {
    name: 'Set up the notification service',
    url: `https://aimstack.readthedocs.io/en/${version}/using/notifications.html`,
  },
  {
    name: 'Define custom callbacks',
    url: `https://aimstack.readthedocs.io/en/${version}/using/callbacks.html`,
  },
  {
    name: 'Host Aim on Kubernetes (K8S)',
    url: `https://aimstack.readthedocs.io/en/${version}/using/k8s_deployment.html`,
  },
  {
    name: 'Run Aim UI on Jupyter Notebook',
    url: `https://aimstack.readthedocs.io/en/${version}/using/jupyter_notebook_ui.html`,
  },
  {
    name: 'Run Aim UI on SageMaker Notebook instance',
    url: `https://aimstack.readthedocs.io/en/${version}/using/sagemaker_notebook_ui.html`,
  },
  {
    name: 'Integration guides',
    url: `https://aimstack.readthedocs.io/en/${version}/using/integration_guides.html`,
  },
  {
    name: 'Data storage - where Aim data is collected',
    url: `https://aimstack.readthedocs.io/en/${version}/understanding/data_storage.html`,
  },
  {
    name: 'Storage indexing - how Aim data is indexed',
    url: `https://aimstack.readthedocs.io/en/${version}/understanding/storage_indexing.html`,
  },
  {
    name: 'Concepts',
    url: `https://aimstack.readthedocs.io/en/${version}/understanding/concepts.html`,
  },
];

export { DOCUMENTATIONS, GUIDES, DEMOS, DASHBOARD_PAGE_GUIDES };
