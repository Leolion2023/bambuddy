import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Loader2, Check, X, Package } from 'lucide-react';
import { api } from '../api/client';
import { Card, CardContent, CardHeader } from './Card';
import { Button } from './Button';
import { useToast } from '../contexts/ToastContext';

export function OrcaSlicerSettings() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [localEnabled, setLocalEnabled] = useState(false);
  const [localPath, setLocalPath] = useState('');
  const [localAutoPush, setLocalAutoPush] = useState(true);
  const [isInitialized, setIsInitialized] = useState(false);

  // Fetch OrcaSlicer status
  const { data: status, isLoading: statusLoading, refetch: refetchStatus } = useQuery({
    queryKey: ['orcaslicer-status'],
    queryFn: api.getOrcaSlicerStatus,
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  // Fetch settings from the backend
  const { data: settings, isLoading: settingsLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: api.getSettings,
  });

  // Initialize local state from settings
  useEffect(() => {
    if (settings) {
      setLocalEnabled(settings.orcaslicer_enabled || false);
      setLocalPath(settings.orcaslicer_path || '');
      setLocalAutoPush(settings.orcaslicer_auto_push_to_archive !== false);
      setIsInitialized(true);
    }
  }, [settings]);

  // Auto-save when settings change (after initial load)
  useEffect(() => {
    if (!isInitialized || !settings) return;

    const hasChanges =
      settings.orcaslicer_enabled !== localEnabled ||
      (settings.orcaslicer_path || '') !== localPath ||
      (settings.orcaslicer_auto_push_to_archive !== false) !== localAutoPush;

    if (hasChanges) {
      const timeoutId = setTimeout(() => {
        saveMutation.mutate();
      }, 500);
      return () => clearTimeout(timeoutId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [localEnabled, localPath, localAutoPush, isInitialized]);

  // Save mutation
  const saveMutation = useMutation({
    mutationFn: () =>
      api.updateSettings({
        orcaslicer_enabled: localEnabled,
        orcaslicer_path: localPath,
        orcaslicer_auto_push_to_archive: localAutoPush,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      queryClient.invalidateQueries({ queryKey: ['orcaslicer-status'] });
      showToast(t('settings.toast.settingsSaved'));
      refetchStatus();
    },
  });

  const isLoading = settingsLoading || statusLoading;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div className="flex items-center gap-2">
          <Package className="w-5 h-5" />
          <h3 className="text-lg font-semibold">{t('orcaslicer.settings.title')}</h3>
        </div>
        {status && (
          <div className="flex items-center gap-2 text-sm">
            {status.available ? (
              <span className="flex items-center gap-1 text-green-600 dark:text-green-400">
                <Check className="w-4 h-4" />
                {t('orcaslicer.status.ready')}
              </span>
            ) : (
              <span className="flex items-center gap-1 text-red-600 dark:text-red-400">
                <X className="w-4 h-4" />
                {status.enabled ? t('orcaslicer.status.notFound') : t('orcaslicer.status.disabled')}
              </span>
            )}
          </div>
        )}
      </CardHeader>

      <CardContent className="space-y-4">
        {isLoading ? (
          <div className="flex items-center justify-center p-8">
            <Loader2 className="w-6 h-6 animate-spin" />
          </div>
        ) : (
          <>
            {/* Enable OrcaSlicer */}
            <div className="flex items-center justify-between">
              <label className="flex flex-col gap-1">
                <span className="font-medium">{t('orcaslicer.settings.enabled')}</span>
              </label>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={localEnabled}
                  onChange={(e) => setLocalEnabled(e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 dark:peer-focus:ring-blue-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-blue-600"></div>
              </label>
            </div>

            {/* OrcaSlicer Path */}
            {localEnabled && (
              <>
                <div className="space-y-2">
                  <label htmlFor="orcaslicer-path" className="flex flex-col gap-1">
                    <span className="font-medium">{t('orcaslicer.settings.pathLabel')}</span>
                    <span className="text-sm text-gray-600 dark:text-gray-400">
                      {t('orcaslicer.settings.pathHelp')}
                    </span>
                  </label>
                  <input
                    id="orcaslicer-path"
                    type="text"
                    value={localPath}
                    onChange={(e) => setLocalPath(e.target.value)}
                    placeholder={t('orcaslicer.settings.pathPlaceholder')}
                    className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-700"
                  />
                  {status?.orcaslicer_path && (
                    <div className="text-sm text-gray-600 dark:text-gray-400">
                      {t('common.current')}: {status.orcaslicer_path}
                    </div>
                  )}
                </div>

                {/* Auto-push to Archive */}
                <div className="flex items-start justify-between gap-4">
                  <label className="flex flex-col gap-1 flex-1">
                    <span className="font-medium">{t('orcaslicer.settings.autoPushToArchive')}</span>
                    <span className="text-sm text-gray-600 dark:text-gray-400">
                      {t('orcaslicer.settings.autoPushToArchiveDesc')}
                    </span>
                  </label>
                  <label className="relative inline-flex items-center cursor-pointer mt-1">
                    <input
                      type="checkbox"
                      checked={localAutoPush}
                      onChange={(e) => setLocalAutoPush(e.target.checked)}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 dark:peer-focus:ring-blue-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-blue-600"></div>
                  </label>
                </div>

                {/* Test Connection Button */}
                <div className="flex gap-2 pt-2">
                  <Button
                    onClick={() => refetchStatus()}
                    disabled={!localEnabled}
                    variant="primary"
                    className="flex-1"
                  >
                    {t('orcaslicer.settings.testConnection')}
                  </Button>
                </div>

                {/* Status Message */}
                {status?.message && (
                  <div className={`text-sm p-3 rounded-lg ${
                    status.available
                      ? 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400'
                      : 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400'
                  }`}>
                    {status.message}
                  </div>
                )}
              </>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
