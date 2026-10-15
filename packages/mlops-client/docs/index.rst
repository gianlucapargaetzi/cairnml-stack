mlops-client
============

The Python client of the MLOps server. It starts runs, records their metrics, parameters and
artifacts, and sends them to the server.

.. code-block:: python

   import mlops

   run = mlops.init(project="vision/seg", name="first-run", config={"lr": 0.1})
   for step in range(3):
       run.log_metric("loss", 1.0 / (step + 1), step=step)
   run.upload_artifact("model.txt", path="model.txt")
   run.close()

.. toctree::
   :maxdepth: 2
   :caption: Reference

   api
