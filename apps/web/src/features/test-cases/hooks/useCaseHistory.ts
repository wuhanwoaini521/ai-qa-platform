import { useState } from 'react';
import { api } from '../../../api/client';
import { TestHistoryResponse } from '../../../types';

export function useCaseHistory() {
  const [caseHistory, setCaseHistory] = useState<TestHistoryResponse | null>(null);
  const [loadingCaseHistory, setLoadingCaseHistory] = useState(false);

  const fetchCaseHistory = async (nodeid: string, projectId: string) => {
    try {
      setLoadingCaseHistory(true);
      const hist = await api.getTestHistory(nodeid, projectId, 20);
      setCaseHistory(hist);
    } catch (err) {
      console.error('Failed to fetch case history', err);
      setCaseHistory(null);
    } finally {
      setLoadingCaseHistory(false);
    }
  };

  return { caseHistory, loadingCaseHistory, fetchCaseHistory, setCaseHistory };
}
