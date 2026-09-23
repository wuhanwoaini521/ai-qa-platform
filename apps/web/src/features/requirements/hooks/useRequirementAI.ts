import { useState } from 'react';
import { api } from '../../../api/client';
import {
  Requirement,
  RequirementAnalysisDTO,
  TestCaseGenerationItem,
  TestCasePriority,
  TestDesign,
  TestDesignCategory,
  TestDesignSuggestion,
} from '../../../types';

interface UseRequirementAIOptions {
  selectedReq: Requirement | null;
  onDesignCreated: (design: TestDesign) => void;
}

export function useRequirementAI({ selectedReq, onDesignCreated }: UseRequirementAIOptions) {
  const [isAiAnalysisOpen, setIsAiAnalysisOpen] = useState(false);
  const [aiAnalysis, setAiAnalysis] = useState<RequirementAnalysisDTO | null>(null);
  const [analyzingReq, setAnalyzingReq] = useState(false);

  const [isAiDesignModalOpen, setIsAiDesignModalOpen] = useState(false);
  const [suggestedDesigns, setSuggestedDesigns] = useState<TestDesignSuggestion[]>([]);
  const [generatingDesigns, setGeneratingDesigns] = useState(false);

  const [isAiCaseModalOpen, setIsAiCaseModalOpen] = useState(false);
  const [suggestedCases, setSuggestedCases] = useState<TestCaseGenerationItem[]>([]);
  const [generatingCases, setGeneratingCases] = useState(false);
  const [activeDesignForCases, setActiveDesignForCases] = useState<TestDesign | null>(null);

  const handleAnalyzeRequirementAI = async () => {
    if (!selectedReq) return;
    try {
      setAnalyzingReq(true);
      setIsAiAnalysisOpen(true);
      const res = await api.analyzeRequirement(selectedReq.id);
      setAiAnalysis(res);
    } catch (err) {
      console.error('AI Requirement analysis failed', err);
    } finally {
      setAnalyzingReq(false);
    }
  };

  const handleGenerateDesignsAI = async () => {
    if (!selectedReq) return;
    try {
      setGeneratingDesigns(true);
      setIsAiDesignModalOpen(true);
      const res = await api.generateTestDesigns(selectedReq.id);
      setSuggestedDesigns(res);
    } catch (err) {
      console.error('AI Test Design generation failed', err);
    } finally {
      setGeneratingDesigns(false);
    }
  };

  const handleAdoptDesign = async (suggestion: TestDesignSuggestion) => {
    if (!selectedReq) return;
    try {
      const created = await api.createTestDesign({
        requirement_id: selectedReq.id,
        title: suggestion.title,
        category: suggestion.category as TestDesignCategory,
        description: suggestion.description,
        risk: suggestion.risk,
        status: 'DRAFT',
      });
      onDesignCreated(created);
      setSuggestedDesigns(suggestedDesigns.filter((s) => s.title !== suggestion.title));
    } catch (err) {
      console.error('Failed to adopt test design', err);
    }
  };

  const handleGenerateCasesAI = async (design: TestDesign) => {
    try {
      setActiveDesignForCases(design);
      setGeneratingCases(true);
      setIsAiCaseModalOpen(true);
      const res = await api.generateTestCases(design.id);
      setSuggestedCases(res);
    } catch (err) {
      console.error('AI Test Case generation failed', err);
    } finally {
      setGeneratingCases(false);
    }
  };

  const handleAdoptCase = async (item: TestCaseGenerationItem) => {
    if (!selectedReq || !activeDesignForCases) return;
    try {
      await api.createTestCase({
        project_id: selectedReq.project_id,
        requirement_id: selectedReq.id,
        test_design_id: activeDesignForCases.id,
        title: item.title,
        preconditions: item.preconditions,
        steps: item.steps,
        expected_result: item.expected_result,
        // AI suggestions may carry a priority outside the union; the API persists it verbatim.
        priority: item.priority as TestCasePriority,
        tags: item.tags,
        automation_status: 'DRAFT',
      });
      setSuggestedCases(suggestedCases.filter((c) => c.title !== item.title));
    } catch (err) {
      console.error('Failed to adopt test case', err);
    }
  };

  return {
    isAiAnalysisOpen,
    setIsAiAnalysisOpen,
    aiAnalysis,
    analyzingReq,
    isAiDesignModalOpen,
    setIsAiDesignModalOpen,
    suggestedDesigns,
    generatingDesigns,
    isAiCaseModalOpen,
    setIsAiCaseModalOpen,
    suggestedCases,
    generatingCases,
    activeDesignForCases,
    handleAnalyzeRequirementAI,
    handleGenerateDesignsAI,
    handleAdoptDesign,
    handleGenerateCasesAI,
    handleAdoptCase,
  };
}
