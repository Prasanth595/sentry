import {Fragment} from 'react';
import {OAuthContextFixture} from 'sentry-fixture/oauth';

import {render, screen, userEvent, within} from 'sentry-test/reactTestingLibrary';

import {ApplicationSummary} from './applicationSummary';
import {ConsentFooter} from './consentNotice';

it('shows granted access and special capabilities in a permission table', async () => {
  render(
    <ApplicationSummary
      context={OAuthContextFixture({
        permissionGroups: [
          {
            resource: 'projects',
            label: 'Projects',
            scopes: ['project:read'],
            actions: ['read'],
            accessDescriptions: {
              read: 'View projects and their settings.',
              write: 'Manage project settings and alert rules, including deleting them.',
              admin: 'Delete projects.',
            },
            description: null,
          },
          {
            resource: 'members',
            label: 'Members',
            scopes: ['member:invite'],
            actions: ['invite'],
            accessDescriptions: {
              read: 'View members.',
              write: 'Update memberships.',
              admin: 'Remove members.',
              invite: 'Invite organization members.',
            },
            description: null,
          },
          {
            resource: 'ci',
            label: 'CI workflows',
            scopes: ['org:ci'],
            actions: [],
            description: 'Upload source maps and create releases.',
          },
        ],
      })}
    />
  );
  const projects = screen.getByRole('row', {
    name: /Projects Granted Not granted Not granted/,
  });
  expect(within(projects).getByRole('img', {name: 'Granted'})).toBeInTheDocument();
  expect(within(projects).getAllByRole('img', {name: 'Not granted'})).toHaveLength(2);
  await userEvent.click(screen.getByRole('rowgroup', {name: 'Permission list'}));
  await userEvent.tab();
  expect(within(projects).getByRole('img', {name: 'Granted'})).toHaveFocus();
  expect(
    await screen.findByText('View projects and their settings.')
  ).toBeInTheDocument();
  expect(
    within(projects).getByRole('img', {name: 'Granted'})
  ).toHaveAccessibleDescription('View projects and their settings.');
  const members = screen.getByRole('row', {name: /Members/});
  expect(within(members).getAllByRole('img', {name: 'Not granted'})).toHaveLength(3);
  await userEvent.hover(
    within(screen.getByRole('row', {name: /CI workflows/})).getByRole('img', {
      name: 'Additional permissions requested',
    })
  );
  expect(
    await screen.findByText('Upload source maps and create releases.')
  ).toBeInTheDocument();
});

it.each([
  ['https://example.com/privacy', null],
  [null, 'https://example.com/terms'],
  ['https://example.com/privacy', 'https://example.com/terms'],
])('links the application policies and revocation settings', (privacyUrl, termsUrl) => {
  render(
    <Fragment>
      <ConsentFooter
        application={{...OAuthContextFixture().application, privacyUrl, termsUrl}}
      />
    </Fragment>
  );
  expect(
    screen.getByRole('link', {name: 'Account → Authorized Applications'})
  ).toHaveAttribute('href', '/settings/account/authorizations/');
  const expected = [privacyUrl, termsUrl].filter(Boolean);
  expect(screen.getAllByRole('link').map(link => link.getAttribute('href'))).toEqual([
    '/settings/account/authorizations/',
    ...expected,
  ]);
});
