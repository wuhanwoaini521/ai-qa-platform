import { useEffect, useState } from 'react';
import { api } from '../../../api/client';
import { Requirement, TestDesign, TestDesignCreate } from '../../../types';

export function useTestDesigns(selectedReq: Requirement | null) {
  const [testDesigns, setTestDesigns] = useState<TestDesign[]>([]);

  const fetchTestDesigns = async (reqId: string) => {
    try {
      const data = await api.getTestDesigns(reqId);
      setTestDesigns(data);
    } catch (err) {
      console.error('Failed to load test designs', err);
    }
  };

  useEffect(() => {
    if (selectedReq) {
      fetchTestDesigns(selectedReq.id);
    } else {
      setTestDesigns([]);
    }
  }, [selectedReq]);

  const createDesign = async (data: TestDesignCreate): Promise<TestDesign | null> => {
    try {
      const created = await api.createTestDesign(data);
      setTestDesigns([created, ...testDesigns]);
      return created;
    } catch (err) {
      console.error('Failed to create test design', err);
      return null;
    }
  };

  const appendDesign = (design: TestDesign) => {
    setTestDesigns([...testDesigns, design]);
  };

  return { testDesigns, createDesign, appendDesign };
}
