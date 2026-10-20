import {useState} from 'react';

import {Avatar} from '@sentry/scraps/avatar';
import {Button} from '@sentry/scraps/button';
import {CompactSelect} from '@sentry/scraps/compactSelect';
import {Flex, Grid, Stack} from '@sentry/scraps/layout';
import {OverlayTrigger} from '@sentry/scraps/overlayTrigger';
import {Text} from '@sentry/scraps/text';

import {t} from 'sentry/locale';
import {ConfigStore} from 'sentry/stores/configStore';

import {ConsentFooter} from './consentNotice';
import type {OAuthApplication, OAuthDecision, OAuthOrganization} from './types';

interface ConsentFormProps {
  application: OAuthApplication;
  busy: boolean;
  disabled: boolean;
  onDecision: (decision: OAuthDecision, organizationId?: string) => void;
  organizations: OAuthOrganization[];
  requiresOrganization: boolean;
}

export function ConsentForm({
  application,
  busy,
  disabled,
  onDecision,
  organizations,
  requiresOrganization,
}: ConsentFormProps) {
  const [organizationId, setOrganizationId] = useState(() => {
    const lastOrganization = ConfigStore.get('lastOrganization');
    return (
      organizations.find(organization => organization.slug === lastOrganization)?.id ??
      organizations[0]?.id
    );
  });
  const selectedOrganization = organizations.find(
    organization => organization.id === organizationId
  );
  return (
    <form
      onSubmit={event => {
        event.preventDefault();
        onDecision('approve', organizationId);
      }}
    >
      <Stack gap="lg">
        {requiresOrganization && selectedOrganization && (
          <Stack gap="sm">
            <Text as="p" size="sm" variant="muted" align="left">
              {t('With access only to…')}
            </Text>
            <Flex
              align="center"
              justify="between"
              gap="lg"
              border="secondary"
              radius="md"
              padding="lg"
            >
              <Flex align="center" gap="md" flex="1" minWidth="0">
                <Avatar
                  type="letter_avatar"
                  identifier={selectedOrganization.slug}
                  name={selectedOrganization.name}
                  size={32}
                />
                <Stack gap="2xs" minWidth="0">
                  <Text bold ellipsis>
                    {selectedOrganization.name}
                  </Text>
                  <Text size="xs" variant="muted" ellipsis>
                    {selectedOrganization.slug}
                  </Text>
                </Stack>
              </Flex>
              <CompactSelect
                value={organizationId}
                options={organizations.map(organization => ({
                  value: organization.id,
                  label: `${organization.name} (${organization.slug})`,
                  leadingItems: (
                    <Avatar
                      type="letter_avatar"
                      identifier={organization.slug}
                      name={organization.name}
                      size={20}
                    />
                  ),
                }))}
                onChange={option => setOrganizationId(option.value)}
                disabled={disabled || organizations.length < 2}
                search
                menuTitle={t('Organization')}
                menuWidth={300}
                position="bottom-end"
                trigger={triggerProps => (
                  <OverlayTrigger.Button
                    {...triggerProps}
                    size="xs"
                    variant="transparent"
                  >
                    {t('Change')}
                  </OverlayTrigger.Button>
                )}
              />
            </Flex>
          </Stack>
        )}
        <Grid columns="3fr 1fr" gap="md" paddingTop="xl">
          <Button
            type="submit"
            variant="primary"
            busy={busy}
            disabled={disabled || (requiresOrganization && !organizationId)}
          >
            {t('Authorize')}
          </Button>
          <Button disabled={disabled} onClick={() => onDecision('deny')}>
            {t('Deny')}
          </Button>
        </Grid>
        <ConsentFooter application={application} />
      </Stack>
    </form>
  );
}
