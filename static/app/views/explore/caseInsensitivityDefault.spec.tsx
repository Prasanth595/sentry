import type {ReactNode} from 'react';
import {OrganizationFixture} from 'sentry-fixture/organization';

import {act, renderHookWithProviders, waitFor} from 'sentry-test/reactTestingLibrary';

import {useCaseInsensitivity} from 'sentry/components/searchQueryBuilder/hooks';
import {LogsAnalyticsPageSource} from 'sentry/utils/analytics/logsAnalyticsEvent';
import {
  ExploreCaseInsensitivityDefault,
  isCaseIndependent,
  useAlwaysMatchesCaseDetails,
} from 'sentry/views/explore/caseInsensitivityDefault';
import {LogsQueryParamsProvider} from 'sentry/views/explore/logs/logsQueryParamsProvider';
import {useSetQueryParamsQuery} from 'sentry/views/explore/queryParams/context';

const organization = OrganizationFixture({features: ['explore-ignore-case-default']});

function Wrapper({children}: {children: ReactNode}) {
  return (
    <LogsQueryParamsProvider
      analyticsPageSource={LogsAnalyticsPageSource.EXPLORE_LOGS}
      source="location"
    >
      <ExploreCaseInsensitivityDefault>{children}</ExploreCaseInsensitivityDefault>
    </LogsQueryParamsProvider>
  );
}

function renderCaseInsensitivity(
  query: Record<string, string>,
  options: {organization?: typeof organization} = {}
) {
  return renderHookWithProviders(
    () => {
      const [caseInsensitive] = useCaseInsensitivity();
      const setQuery = useSetQueryParamsQuery();
      return {caseInsensitive, setQuery};
    },
    {
      additionalWrapper: Wrapper,
      organization: options.organization ?? organization,
      initialRouterConfig: {
        location: {pathname: '/organizations/org-slug/explore/logs/', query},
      },
    }
  );
}

describe('ExploreCaseInsensitivityDefault', () => {
  it('ignores case and records it in the URL when nothing is filtered', async () => {
    const {result, router} = renderCaseInsensitivity({});

    await waitFor(() => expect(router.location.query.caseInsensitive).toBe('1'));
    expect(result.current.caseInsensitive).toBe(true);
  });

  it('matches case and records it in the URL when an existing link has a filter', async () => {
    const {result, router} = renderCaseInsensitivity({logsQuery: 'message:Deleted'});

    await waitFor(() => expect(router.location.query.caseInsensitive).toBe('0'));
    expect(result.current.caseInsensitive).toBe(false);
  });

  it('keeps an explicit setting when nothing is filtered', async () => {
    const {result, router} = renderCaseInsensitivity({caseInsensitive: '0'});

    await waitFor(() => expect(result.current.caseInsensitive).toBe(false));
    expect(router.location.query.caseInsensitive).toBe('0');
  });

  it('keeps ignoring case when a filter is typed after defaulting', async () => {
    const {result, router} = renderCaseInsensitivity({});
    await waitFor(() => expect(router.location.query.caseInsensitive).toBe('1'));

    act(() => result.current.setQuery('message:Deleted'));

    await waitFor(() => expect(router.location.query.logsQuery).toBe('message:Deleted'));
    expect(router.location.query.caseInsensitive).toBe('1');
    expect(result.current.caseInsensitive).toBe(true);
  });

  it('leaves the URL alone when the feature is disabled', async () => {
    const {result, router} = renderCaseInsensitivity(
      {},
      {organization: OrganizationFixture()}
    );

    await waitFor(() => expect(result.current.caseInsensitive).toBeNull());
    expect(router.location.query.caseInsensitive).toBeUndefined();
  });
});

describe('isCaseIndependent', () => {
  it('returns true when nothing is filtered', () => {
    expect(isCaseIndependent({query: '', yAxes: ['count(message)']})).toBe(true);
  });

  it('returns false when the query has a filter', () => {
    expect(isCaseIndependent({query: 'message:Deleted', yAxes: []})).toBe(false);
  });

  it('returns false when a y-axis has a conditional filter', () => {
    expect(
      isCaseIndependent({query: '', yAxes: ['count_if(`message:Deleted`,message)']})
    ).toBe(false);
  });

  it('returns false when a cross event has a query', () => {
    expect(
      isCaseIndependent({
        query: '',
        yAxes: [],
        crossEvents: [{type: 'logs', query: 'message:Deleted'}],
      })
    ).toBe(false);
  });
});

describe('useAlwaysMatchesCaseDetails', () => {
  function renderDetails(query: string, caseInsensitive: string) {
    return renderHookWithProviders(
      () => useAlwaysMatchesCaseDetails({query, yAxes: ['count(message)']}),
      {
        organization,
        initialRouterConfig: {
          location: {
            pathname: '/organizations/org-slug/explore/logs/',
            query: {caseInsensitive},
          },
        },
      }
    );
  }

  it('returns a note when ignoring case on a filtered view', () => {
    const {result} = renderDetails('message:Deleted', '1');

    expect(result.current).toBe('Always matches case');
  });

  it('returns nothing when nothing is filtered', () => {
    const {result} = renderDetails('', '1');

    expect(result.current).toBeNull();
  });

  it('returns nothing when matching case', () => {
    const {result} = renderDetails('message:Deleted', '0');

    expect(result.current).toBeNull();
  });
});
