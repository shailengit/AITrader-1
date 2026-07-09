import ChartView from '../app/ScreenerBuilder/ChartView';

/**
 * Markov-specific full-page chart view.
 * Wraps the shared ChartView with Markov-specific back-button and referrer labels.
 */
export default function MarkovChartView() {
  return (
    <ChartView
      backLabel="Back to Markov Chain Trader"
      backPath="/markov"
      referrerPath="/markov"
      referrerLabel="Markov Chain Trader"
    />
  );
}
