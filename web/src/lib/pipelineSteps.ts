/** The 4 real pipeline artifact types currently wired into the web app,
 * in the order run_web_job.py processes them (dependency order matters:
 * DSD/Key Family reads back Concept Scheme + Codelists output; Dataflow
 * reads back DSD/Key Family output). */
export const PIPELINE_STEPS = ["CONCEPT_SCHEME", "CODELISTS", "DSD_KEY_FAMILY", "DATAFLOW"] as const;
export type PipelineStepKey = (typeof PIPELINE_STEPS)[number];

export const STEP_LABELS: Record<PipelineStepKey, string> = {
  CONCEPT_SCHEME: "Concept Scheme",
  CODELISTS: "Codelists",
  DSD_KEY_FAMILY: "DSD / Key Family",
  DATAFLOW: "Dataflow",
};

/** Matches pipeline/artifacts.py's artifact_folder_name() for these keys. */
export const STEP_ARTIFACT_FOLDER: Record<PipelineStepKey, string> = {
  CONCEPT_SCHEME: "Concept Scheme",
  CODELISTS: "Codelists",
  DSD_KEY_FAMILY: "DSD Key Family",
  DATAFLOW: "Dataflow",
};
