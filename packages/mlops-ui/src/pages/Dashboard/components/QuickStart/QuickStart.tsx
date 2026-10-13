import * as React from 'react';

import { Text } from 'components/kit';
import CodeBlock from 'components/CodeBlock/CodeBlock';

import './QuickStart.scss';

function QuickStart() {
  return (
    <div className='QuickStart'>
      <Text
        tint={100}
        weight={600}
        size={18}
        className='Dashboard__middle__title'
      >
        Quick Start
      </Text>
      <div className='QuickStart__section'>
        <Text
          component='h3'
          size={14}
          weight={700}
          tint={100}
          className='QuickStart__section__title'
        >
          Integrate MLOps Flow with your code
        </Text>
        <CodeBlock
          code={`import mlops

# Start a run in an experiment of a project
run = mlops.init(project="vision/segmentation", name="baseline",
                 experiment="training")

# Log run parameters
run["hparams"] = {
    "learning_rate": 0.001,
    "batch_size": 32
}

# Log metrics
for i in range(10):
    run.track(i, name='loss', step=i, context={ "subset":"train" })
    run.track(i, name='acc', step=i, context={ "subset":"train" })`}
        />
      </div>
    </div>
  );
}

export default QuickStart;
