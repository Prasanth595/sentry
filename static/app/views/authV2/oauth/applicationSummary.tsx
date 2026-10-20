import {IconLink} from '@sentry/icons/link';

import {Avatar} from '@sentry/scraps/avatar';
import {Flex, Stack} from '@sentry/scraps/layout';
import {ExternalLink} from '@sentry/scraps/link';
import {Text} from '@sentry/scraps/text';

import {t} from 'sentry/locale';

import {PermissionTable} from './permissionTable';
import type {OAuthContext} from './types';

export function ApplicationSummary({
  context,
  userCode,
}: {
  context: OAuthContext;
  userCode?: string;
}) {
  const {application, permissions, permissionGroups} = context;
  const homepageOrigin =
    application.homepageUrl && URL.canParse(application.homepageUrl)
      ? new URL(application.homepageUrl).origin
      : null;
  return (
    <Stack gap="sm">
      <Text as="p" size="sm" variant="muted" align="left">
        {t("You're authorizing…")}
      </Text>
      <Stack border="secondary" radius="md" overflow="hidden">
        <Flex align="center" gap="md" padding="lg">
          <Avatar
            type="letter_avatar"
            identifier={application.clientId}
            name={application.name}
            size={32}
          />
          <Stack gap="2xs" flex="1" minWidth="0">
            <Text bold ellipsis>
              {application.name}
            </Text>
            {application.homepageUrl && homepageOrigin && (
              <Text size="xs" variant="muted">
                <ExternalLink href={application.homepageUrl}>
                  {homepageOrigin}
                </ExternalLink>
              </Text>
            )}
          </Stack>
          {userCode && (
            <Flex
              align="center"
              gap="xs"
              background="secondary"
              radius="md"
              padding="sm md"
            >
              <IconLink size="xs" variant="muted" />
              <Text
                size="md"
                variant="muted"
                monospace
                wrap="nowrap"
                aria-label={t('Confirm that this code matches your device: %s', userCode)}
              >
                {userCode}
              </Text>
            </Flex>
          )}
        </Flex>
        {permissionGroups ? (
          <PermissionTable groups={permissionGroups} />
        ) : (
          <Stack
            as="ul"
            gap="xs"
            padding="lg"
            paddingLeft="xl"
            borderTop="secondary"
            maxHeight="280px"
            overflow="auto"
          >
            {permissions.map(permission => (
              <li key={permission}>
                <Text>{permission}</Text>
              </li>
            ))}
          </Stack>
        )}
      </Stack>
    </Stack>
  );
}
