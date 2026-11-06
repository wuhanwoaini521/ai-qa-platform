import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { BrowserRouter } from 'react-router-dom';
import { DesignSystemProvider } from '@self/ui-style/react';
import { setAuthToken, setUnauthorizedHandler, hasAuthToken } from './api/client';
import { AppRoutes } from './app/routes';
import { LoginScreen } from './app/LoginScreen';
import { PreferencesProvider } from './app/Preferences';
import { ProjectScopeProvider } from './app/ProjectScope';

export const App: React.FC = () => {
  const [authenticated, setAuthenticated] = useState<boolean>(() => hasAuthToken());
  const { i18n } = useTranslation();

  useEffect(() => {
    setUnauthorizedHandler(() => setAuthenticated(false));
    return () => setUnauthorizedHandler(null);
  }, []);

  const handleSignOut = useCallback(() => {
    setAuthToken(null);
    setAuthenticated(false);
  }, []);

  const appContent = authenticated ? (
    <BrowserRouter>
      <ProjectScopeProvider>
        <AppRoutes onSignOut={handleSignOut} />
      </ProjectScopeProvider>
    </BrowserRouter>
  ) : (
    <LoginScreen onAuthenticated={() => setAuthenticated(true)} />
  );

  return (
    <PreferencesProvider>
      <DesignSystemProvider
        className="app-design-system"
        locale={i18n.resolvedLanguage ?? i18n.language}
        dotted
      >
        {appContent}
      </DesignSystemProvider>
    </PreferencesProvider>
  );
};
