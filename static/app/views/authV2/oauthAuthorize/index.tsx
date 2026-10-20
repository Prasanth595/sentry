import {Alert} from '@sentry/scraps/alert';
import {Button} from '@sentry/scraps/button';
import {Stack} from '@sentry/scraps/layout';
import {Text} from '@sentry/scraps/text';

import {t} from 'sentry/locale';
import {getRequestErrorUserMessage} from 'sentry/utils/requestError/getRequestErrorUserMessage';
import {AccountBadge} from 'sentry/views/authV2/components/accountBadge';
import {ApplicationSummary} from 'sentry/views/authV2/oauth/applicationSummary';
import {ConsentForm} from 'sentry/views/authV2/oauth/consentForm';
import {OAuthAuthentication} from 'sentry/views/authV2/oauth/oauthAuthentication';
import {OAuthFlowTransition} from 'sentry/views/authV2/oauth/oauthFlowTransition';
import {OAuthLayout} from 'sentry/views/authV2/oauth/oauthLayout';
import {useBrandedAuthLoading} from 'sentry/views/authV2/useBrandedAuthLoading';

import {useOAuthAuthorizeFlow} from './useOAuthAuthorizeFlow';

export default function OAuthAuthorize() {
  const {state, actions} = useOAuthAuthorizeFlow();
  const isLoading = state.status === 'loading' || state.status === 'submitting';
  useBrandedAuthLoading(isLoading);
  if (isLoading) {
    return null;
  }

  return (
    <OAuthLayout>
      {state.context && <ApplicationSummary context={state.context} />}
      <OAuthFlowTransition step={state.status}>
        {state.context && state.user?.id && state.status !== 'authentication' && (
          <Stack gap="sm">
            <Text as="p" size="sm" variant="muted" align="left">
              {t('With your account…')}
            </Text>
            <AccountBadge
              user={state.user}
              isSwitchingAccount={state.isSwitchingAccount}
              disabled={state.isSubmitting}
              onSwitchAccount={actions.switchAccount}
            />
          </Stack>
        )}
        {state.switchError && (
          <Alert variant="danger">{getRequestErrorUserMessage(state.switchError)}</Alert>
        )}
        {state.status === 'authentication' && (
          <OAuthAuthentication
            authConfig={state.authConfig}
            isPreparingConsent={state.isPreparingConsent}
            onAuthenticated={actions.onAuthenticated}
            returnTo={state.returnTo}
          />
        )}
        {state.status === 'consent' && (
          <ConsentForm
            application={state.context.application}
            key={state.consent.transactionId}
            busy={state.isSubmitting}
            disabled={state.busy}
            organizations={state.consent.organizationOptions}
            requiresOrganization={state.context.application.requiresOrgLevelAccess}
            onDecision={actions.decide}
          />
        )}
        {state.status === 'error' && <Alert variant="danger">{state.message}</Alert>}
        {state.status === 'error' && state.canRetry && (
          <Button onClick={actions.retry}>{t('Start over')}</Button>
        )}
      </OAuthFlowTransition>
    </OAuthLayout>
  );
}
