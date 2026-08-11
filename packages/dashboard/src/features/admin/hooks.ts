// packages/dashboard/src/features/admin/hooks.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  adminApi,
  type UserPatch,
  type UserCreate,
  type OperatorCreate,
  type OperatorPatch,
} from '@/features/admin/api'

export const adminKeys = {
  all: ['admin'] as const,
  users: () => [...adminKeys.all, 'users'] as const,
  team: () => [...adminKeys.all, 'team'] as const,
  roles: () => [...adminKeys.all, 'roles'] as const,
  operatorRoles: () => [...adminKeys.all, 'operator-roles'] as const,
  regions: () => [...adminKeys.all, 'regions'] as const,
}

export function useAdminUsers() {
  return useQuery({
    queryKey: adminKeys.users(),
    queryFn: adminApi.listUsers,
  })
}

export function useAdminRoles() {
  return useQuery({
    queryKey: adminKeys.roles(),
    queryFn: adminApi.listRoles,
  })
}

export function useAdminRegions() {
  return useQuery({
    queryKey: adminKeys.regions(),
    queryFn: adminApi.listRegions,
    staleTime: 5 * 60 * 1000,
  })
}

export function useCreateUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: UserCreate) => adminApi.createUser(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminKeys.users() })
    },
  })
}

export function useSupervisorTeam() {
  return useQuery({
    queryKey: adminKeys.team(),
    queryFn: adminApi.listOperators,
  })
}

export function useCreateOperator() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: OperatorCreate) => adminApi.createOperator(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminKeys.team() })
    },
  })
}

export function useUpdateOperator() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ userId, patch }: { userId: number; patch: OperatorPatch }) =>
      adminApi.updateOperator(userId, patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminKeys.team() })
    },
  })
}

export function useOperatorRoles() {
  return useQuery({
    queryKey: adminKeys.operatorRoles(),
    queryFn: adminApi.listOperatorRoles,
  })
}

export function useUpdateUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ userId, patch }: { userId: number; patch: UserPatch }) =>
      adminApi.updateUser(userId, patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminKeys.users() })
    },
  })
}