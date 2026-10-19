import {useTheme} from '@emotion/react';
import {AnimatePresence, motion} from 'framer-motion';

import {Alert} from '@sentry/scraps/alert';
import {Button} from '@sentry/scraps/button';
import {OTPInput} from '@sentry/scraps/input';
import {Container, Stack} from '@sentry/scraps/layout';
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

import {useOAuthDeviceFlow} from './useOAuthDeviceFlow';

export default function OAuthDevice() {
  const {state, actions} = useOAuthDeviceFlow();
  const theme = useTheme();
  useBrandedAuthLoading(false);

  return (
    <OAuthLayout>
      <OAuthFlowTransition
        step={state.status === 'code-entry' ? 'code-entry' : 'authorization'}
      >
        {state.context && (
          <ApplicationSummary context={state.context} userCode={state.context.userCode} />
        )}
        <OAuthFlowTransition step={state.status}>
          {state.status === 'code-entry' && (
            <Stack gap="xl" align="center">
              <Text as="p" align="center">
                {t('Enter the code shown on your device.')}
              </Text>
              <OTPInput
                aria-label={t('Device code')}
                format="AAAA-AAAA"
                uppercase
                defaultValue={state.userCode.replace(/-/g, '').toUpperCase()}
                disabled={state.isPreparingCode}
                onComplete={actions.enterCode}
              />
              <AnimatePresence>
                {state.message && (
                  <MotionContainer
                    width="100%"
                    key={state.message}
                    initial={{y: 10, opacity: 0}}
                    animate={{y: 0, opacity: 1}}
                    exit={{y: 10, opacity: 0}}
                    transition={theme.motion.framer.smooth.moderate}
                  >
                    <Alert variant="danger">{state.message}</Alert>
                  </MotionContainer>
                )}
              </AnimatePresence>
            </Stack>
          )}
          {state.user?.id && state.status === 'consent' && (
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
            <Alert variant="danger">
              {getRequestErrorUserMessage(state.switchError)}
            </Alert>
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
              key={state.sessionKey}
              busy={state.isSubmitting}
              disabled={state.busy}
              organizations={state.consent.organizationOptions}
              requiresOrganization={state.context.application.requiresOrgLevelAccess}
              onDecision={actions.decide}
            />
          )}
          {state.status === 'complete' && (
            <Alert
              variant={state.outcome === 'approved' ? 'success' : 'warning'}
              showIcon={false}
            >
              {state.outcome === 'approved'
                ? t('Application authorized. Return to your device to continue.')
                : t('Authorization denied. You can close this window.')}
            </Alert>
          )}
          {state.status === 'error' && <Alert variant="danger">{state.message}</Alert>}
          {state.status === 'error' && state.canRetry && (
            <Button onClick={actions.retry}>{t('Start over')}</Button>
          )}
        </OAuthFlowTransition>
      </OAuthFlowTransition>
    </OAuthLayout>
  );
}

const MotionContainer = motion.create(Container);
