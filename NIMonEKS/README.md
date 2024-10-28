# Vista-3D NIM on EKS

The Versatile Imaging SegmenTation and Annotation ([VISTA](https://docs.nvidia.com/ai-enterprise/nim-medical-imaging/latest/vista-3d.html)) model combines semantic segmentation with interactivity, offering high accuracy and adaptability across diverse anatomical areas for medical imaging.

![NIM on EKS architecture diagram](../Figures/aws-eks-architecture.png)

## Pre-Requisites

* [EKS Cluster](https://github.com/awslabs/data-on-eks/tree/main/ai-ml/bionemo)
* Install [aws-load-balancer-controller](https://docs.aws.amazon.com/eks/latest/userguide/lbc-helm.html)
* Install [EBS CSI](https://docs.aws.amazon.com/eks/latest/userguide/workloads-add-ons-available-eks.html#add-ons-aws-ebs-csi-driver) Add-On 
* Install EKS Add-on [Amazon Cloudwatch Observability](https://docs.aws.amazon.com/eks/latest/userguide/workloads-add-ons-available-eks.html#amazon-cloudwatch-observability) to view Container Insights
* [Kubectl](https://kubernetes.io/docs/tasks/tools/)
* [Helm](https://helm.sh/docs/helm/helm_install/) kubernetes deployment tool
* Install [3D Slicer](https://www.slicer.org/) to view .nrrd files returned from vista3d

## Setup NVIDIA Developer Account

Procure a NGC API KEY from [NVIDIA](https://catalog.ngc.nvidia.com/) to pull images from NGC. Create an account and provision an API Key.

## NGC Docker Images

Docker Login to NGC registry

```bash
echo "$NGC_API_KEY" | docker login nvcr.io --username '$oauthtoken' --password-stdin
```

Pull the vista3d image

```bash
docker pull nvcr.io/nvidia/nim/medical_imaging_vista3d
```

Run the image and create a shell to investigate the container

```bash
docker run -it $IMAGE_ID sh
```

## Deploy the NIM to an EKS Cluster Using the NIM-Deploy Helm chart

Create a Kubernetes namespace for vista to deploy the NIM

```bash
kubectl create ns vista
```

Deploy the vista NIM from this repo using nim-deploy helm chart

```bash
export NGC_API_KEY=<NGC_API_KEY_HERE>
helm --namespace vista install vista eks/helm/nim-llm/ --create-namespace --set model.ngcAPIKey="$NGC_API_KEY" -f vista3d-values.yaml
```

Check your pods to ensure they are up and healthy. Pods should be in a Running state and 1/1 Ready status.

```bash
kubectl get pods -n vista -o wide
NAME      READY   STATUS    RESTARTS   AGE     IP               NODE                                          NOMINATED NODE   READINESS GATES
vista-0   1/1     Running   0          5h43m   100.64.125.210   ip-100-64-89-163.us-west-2.compute.internal   <none>           <none>
vista-1   1/1     Running   0          4h26m   100.64.2.130     ip-100-64-89-163.us-west-2.compute.internal   <none>           <none>
```

Check your Kubernetes services to ensure they are listening on port 8008 for your NIM inference API endpoints.

```bash
kubectl get svc -n vista -o wide
NAME                TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)    AGE   SELECTOR
vista-nim-llm       ClusterIP   172.20.23.115   <none>        8008/TCP   28h   app.kubernetes.io/instance=vista,app.kubernetes.io/name=nim-llm
vista-nim-llm-sts   ClusterIP   None            <none>        8008/TCP   28h   app.kubernetes.io/instance=vista,app.kubernetes.io/name=nim-llm
```

Setup an ALB Controller Ingress to allow traffic to the NIM Inference endpoints.

Follow these docs to install the [AWS ALB Ingress Controller](https://kubernetes-sigs.github.io/aws-load-balancer-controller/v2.2/deploy/installation/) 

Deploy the AWS ALB Ingress from the ingress.yaml configuration file to expose the vista3d NIM

```bash
kubectl apply -f eks/ingress.yaml
```

Check the public address of your ALB generated from the ALB Controller

```bash
kubectl get ing -n vista -o wide
NAME          CLASS   HOSTS   ADDRESS                                                                PORTS   AGE
nim-llm-alb   alb     *       k8s-vista-nimllmal-1951141444-1058888912.us-west-2.elb.amazonaws.com   80      5h42m
```

With the public ALB domain address you can now make requests to your vista3d image endpoint.

```bash
curl -X POST http://{ALB_ADDRESS_HERE}/vista3d/inference \
-H "Content-Type: application/json" \
--output output.nrrd \
-d '{
    "image": "https://assets.ngc.nvidia.com/products/api-catalog/vista3d/example-1.nii.gz",
    "prompts": {
        "classes": ["lung", "heart"]
    }
}'
```

An output file will be created, `output.nrrd`, open it with 3D Slicer if you want to see the result.

## NIM-Deploy Helm Values

### nim-llm

![Version: 1.1.2](https://img.shields.io/badge/Version-1.1.2-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 1.0.3](https://img.shields.io/badge/AppVersion-1.0.3-informational?style=flat-square)

A Helm chart for NVIDIA NIM for LLMs

#### Requirements

Kubernetes: `>=v1.23.0-0`

#### Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| affinity | object | `{}` |  |
| autoscaling.enabled | bool | `false` |  |
| autoscaling.maxReplicas | int | `10` |  |
| autoscaling.metrics | list | `[]` |  |
| autoscaling.minReplicas | int | `1` |  |
| containerSecurityContext | object | `{}` |  |
| customArgs | list | `[]` |  |
| customCommand | list | `[]` |  |
| env | list | `[]` |  |
| extraVolumeMounts | object | `{}` |  |
| extraVolumes | object | `{}` |  |
| healthPort | int | `8000` |  |
| hostPath.enabled | bool | `false` |  |
| hostPath.path | string | `"/model-store"` |  |
| image.pullPolicy | string | `"IfNotPresent"` |  |
| image.repository | string | `"nvcr.io/nim/meta/llama3-8b-instruct"` |  |
| image.tag | string | `""` |  |
| imagePullSecrets[0].name | string | `"ngc-secret"` |  |
| ingress.annotations | object | `{}` |  |
| ingress.className | string | `""` |  |
| ingress.enabled | bool | `false` |  |
| ingress.hosts[0].host | string | `"chart-example.local"` |  |
| ingress.hosts[0].paths[0].path | string | `"/"` |  |
| ingress.hosts[0].paths[0].pathType | string | `"ImplementationSpecific"` |  |
| ingress.hosts[0].paths[0].serviceType | string | `"openai"` |  |
| ingress.tls | list | `[]` |  |
| initContainers.extraInit | list | `[]` |  |
| initContainers.ngcInit | object | `{}` |  |
| livenessProbe.command[0] | string | `"myscript.sh"` |  |
| livenessProbe.enabled | bool | `true` |  |
| livenessProbe.failureThreshold | int | `3` |  |
| livenessProbe.initialDelaySeconds | int | `15` |  |
| livenessProbe.method | string | `"http"` |  |
| livenessProbe.path | string | `"/v1/health/live"` |  |
| livenessProbe.periodSeconds | int | `10` |  |
| livenessProbe.successThreshold | int | `1` |  |
| livenessProbe.timeoutSeconds | int | `1` |  |
| metrics.enabled | bool | `true` |  |
| metrics.serviceMonitor.additionalLabels | object | `{}` |  |
| metrics.serviceMonitor.enabled | bool | `false` |  |
| model.jsonLogging | bool | `true` |  |
| model.labels | object | `{}` |  |
| model.legacyCompat | bool | `false` |  |
| model.logLevel | string | `"INFO"` |  |
| model.modelStorePath | string | `""` |  |
| model.name | string | `"meta/llama3-8b-instruct"` |  |
| model.ngcAPIKey | string | `""` |  |
| model.ngcAPISecret | string | `"ngc-api"` |  |
| model.nimCache | string | `"/model-store"` |  |
| model.numGpus | int | `1` |  |
| model.openaiPort | int | `8000` |  |
| model.subPath | string | `"model-store"` |  |
| multiNode.clusterStartTimeout | int | `300` |  |
| multiNode.enabled | bool | `false` |  |
| multiNode.gpusPerNode | int | `1` |  |
| multiNode.leaderWorkerSet.enabled | bool | `true` |  |
| multiNode.mpiJob.launcherResources | object | `{}` |  |
| multiNode.mpiJob.workerAnnotations | object | `{}` |  |
| multiNode.optimized.enabled | bool | `true` |  |
| multiNode.workers | int | `1` |  |
| nfs.enabled | bool | `false` |  |
| nfs.path | string | `"/exports"` |  |
| nfs.readOnly | bool | `false` |  |
| nfs.server | string | `"nfs-server.example.com"` |  |
| nodeSelector | object | `{}` |  |
| persistence.accessMode | string | `"ReadWriteOnce"` |  |
| persistence.annotations | object | `{}` |  |
| persistence.enabled | bool | `false` |  |
| persistence.existingClaim | string | `""` |  |
| persistence.size | string | `"50Gi"` |  |
| persistence.storageClass | string | `""` |  |
| persistence.stsPersistentVolumeClaimRetentionPolicy.whenDeleted | string | `"Retain"` |  |
| persistence.stsPersistentVolumeClaimRetentionPolicy.whenScaled | string | `"Retain"` |  |
| podAnnotations | object | `{}` |  |
| podSecurityContext.fsGroup | int | `1000` |  |
| podSecurityContext.runAsGroup | int | `1000` |  |
| podSecurityContext.runAsUser | int | `1000` |  |
| readinessProbe.enabled | bool | `true` |  |
| readinessProbe.failureThreshold | int | `3` |  |
| readinessProbe.initialDelaySeconds | int | `15` |  |
| readinessProbe.path | string | `"/v1/health/ready"` |  |
| readinessProbe.periodSeconds | int | `10` |  |
| readinessProbe.successThreshold | int | `1` |  |
| readinessProbe.timeoutSeconds | int | `1` |  |
| replicaCount | int | `1` |  |
| resources.limits."nvidia.com/gpu" | int | `1` |  |
| service.annotations | object | `{}` |  |
| service.labels | object | `{}` |  |
| service.name | string | `""` |  |
| service.openaiPort | int | `8000` |  |
| service.type | string | `"ClusterIP"` |  |
| serviceAccount.annotations | object | `{}` |  |
| serviceAccount.create | bool | `false` |  |
| serviceAccount.name | string | `""` |  |
| startupProbe.enabled | bool | `true` |  |
| startupProbe.failureThreshold | int | `180` |  |
| startupProbe.initialDelaySeconds | int | `40` |  |
| startupProbe.path | string | `"/v1/health/ready"` |  |
| startupProbe.periodSeconds | int | `10` |  |
| startupProbe.successThreshold | int | `1` |  |
| startupProbe.timeoutSeconds | int | `1` |  |
| statefulSet.enabled | bool | `true` |  |
| tolerations[0].effect | string | `"NoSchedule"` |  |
| tolerations[0].key | string | `"nvidia.com/gpu"` |  |
| tolerations[0].operator | string | `"Exists"` |  |

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.14.2](https://github.com/norwoodj/helm-docs/releases/v1.14.2)
