import React, { useCallback, useEffect, useState } from 'react';
import { BrowserRouter } from 'react-router-dom';
import { setAuthToken, setUnauthorizedHandler, hasAuthToken } from './api/client';
import { AppRoutes } from './app/routes';
import { LoginScreen } from './app/LoginScreen';
import { PreferencesProvider } from './app/Preferences';
import { ProjectScopeProvider } from './app/ProjectScope';

export const App: React.FC = () => {
  const [authenticated, setAuthenticated] = useState<boolean>(() => hasAuthToken());

  useEffect(() => {
    setUnauthorizedHandler(() => setAuthenticated(false));
    return () => setUnauthorizedHandler(null);
  }, []);

  const handleSignOut = useCallback(() => {
    setAuthToken(null);
    setAuthenticated(false);
  }, []);

  if (!authenticated) {
    return <LoginScreen onAuthenticated={() => setAuthenticated(true)} />;
  }

  return (
    <BrowserRouter>
      <PreferencesProvider>
        <ProjectScopeProvider>
          <AppRoutes onSignOut={handleSignOut} />
        </ProjectScopeProvider>
      </PreferencesProvider>
    </BrowserRouter>
  );
};
