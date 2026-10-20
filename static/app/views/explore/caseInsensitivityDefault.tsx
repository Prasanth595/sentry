import {useEffect, type ReactNode} from 'react';

import {
  CaseInsensitivityDefaultContext,
  useCaseInsensitivity,
  useCaseInsensitivityParam,
} from 'sentry/components/searchQueryBuilder/hooks';
import {t} from 'sentry/locale';
import type {Organization} from 'sentry/types/organization';
import {useOrganization} from 'sentry/utils/useOrganization';
import {
  useQueryParamsCrossEvents,
  useQueryParamsQuery,
  useQueryParamsVisualizes,
} from 'sentry/views/explore/queryParams/context';
import type {CrossEvent} from 'sentry/views/explore/queryParams/crossEvent';
import {IF_SUFFIX} from 'sentry/views/explore/utils/parseConditionalAggregate';

export function hasIgnoreCaseDefault(organization: Organization) {
  return organization.features.includes('explore-ignore-case-default');
}

interface CaseIndependenceOptions {
  query: string;
  yAxes: readonly string[];
  crossEvents?: readonly CrossEvent[] | null;
}

// Links and saved queries without a case setting have always matched case, so ignoring
// case by default is only safe when nothing in them could match differently.
export function isCaseIndependent({query, yAxes, crossEvents}: CaseIndependenceOptions) {
  return (
    query === '' &&
    !yAxes.some(yAxis => yAxis.includes(`${IF_SUFFIX}(`)) &&
    !crossEvents?.some(crossEvent => crossEvent.query !== '')
  );
}

export function useAlwaysMatchesCaseDetails({
  query,
  yAxes,
}: Omit<CaseIndependenceOptions, 'crossEvents'>) {
  const organization = useOrganization();
  const [caseInsensitive] = useCaseInsensitivity();

  if (
    !hasIgnoreCaseDefault(organization) ||
    !caseInsensitive ||
    isCaseIndependent({query, yAxes})
  ) {
    return null;
  }

  return t('Always matches case');
}

export function ExploreCaseInsensitivityDefault({children}: {children: ReactNode}) {
  const organization = useOrganization();
  const query = useQueryParamsQuery();
  const visualizes = useQueryParamsVisualizes();
  const crossEvents = useQueryParamsCrossEvents();
  const [caseInsensitive, setCaseInsensitive] = useCaseInsensitivityParam();

  const defaultCaseInsensitive =
    hasIgnoreCaseDefault(organization) && caseInsensitive === null
      ? isCaseIndependent({
          query,
          yAxes: visualizes.map(visualize => visualize.yAxis),
          crossEvents,
        })
      : null;

  useEffect(() => {
    if (caseInsensitive === null && defaultCaseInsensitive !== null) {
      setCaseInsensitive(defaultCaseInsensitive);
    }
  }, [caseInsensitive, defaultCaseInsensitive, setCaseInsensitive]);

  return (
    <CaseInsensitivityDefaultContext value={defaultCaseInsensitive}>
      {children}
    </CaseInsensitivityDefaultContext>
  );
}
