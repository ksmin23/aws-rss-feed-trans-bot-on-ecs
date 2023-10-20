# AWS Recent Announcements Rss Feed Translation Bot

영문 [AWS의 최신 소식 (What's New with AWS?)](https://aws.amazon.com/new/)을 한국어로
기계 번역해서 영문과 한국어 번역 내용(아래 그림 참조)을 email로 전송해주는 프로젝트.<br/>

  **Figure 1.** 영문 AWS의 최신 소식을 한국어로 번역한 결과
  ![rss_feed_trans_bot_results](./assets/rss_feed_trans_bot_results.png)

## Architecture
  ![rss-feed-trans-bot-arch](./assets/rss-feed-trans-bot-arch.svg)

## Deployment
### Build & Push Docker Image
1. ECR Repository를 생성한다.
  예를 들어, `transbot/rssfeed` 이름의 Repository를 생성한다.

2. Docker 이미지를 빌드한다.

    ```
    $ docker build -t aws_rss_feed_transbot:{tag} \
        --build-arg region_name="{aws-region-name}" \
        --build-arg my_s3_bucket_name="{s3-bucket-name}" \
        --build-arg sender_email="{sender@email.com}" \
        --build-arg receiver_emails="{receiver1@email.com,receiver2@email.com,receiver3@email.com}" \
        --build-arg cache_host="{localhost}" ./
    ```
    `my_s3_bucket_name` 는 `aws-rss-feed-{region}-{suffix}` 형식으로 지정한다.
    (예: `aws-rss-feed-us-east-1-hq4t378`)

3. Docker 이미지 태그를 생성한다.
    ```
    $ docker tag aws_rss_feed_transbot:{tag} {account_id}.dkr.ecr.{region}.amazonaws.com/{repository_name}:{tag}
    ```

4. Docker 이미지를 ECR Repository에 push 하기 위해서 Amazon ECR Registry에 인증을 획득한다.

    ```
    $ aws ecr get-login-password --region {region} | docker login --username AWS --password-stdin {account_id}.dkr.ecr.{region}.amazonaws.com
    ```

5. ECR Repository를 생성한다.

    ```
    $ aws ecr create-repository --repository-name {repository_name}
    ```

6. Docker 이미지를 ECR Repository에 push 한다.

    ```
    $ docker push {account_id}.dkr.ecr.{region}.amazonaws.com/{repository_name}:{tag}
    ```

### Deploy ECS Scheduled Task
1. [Getting Started With the AWS CDK](https://docs.aws.amazon.com/cdk/latest/guide/getting_started.html)를 참고해서 cdk를 설치하고,
cdk를 실행할 때 사용할 IAM User를 생성한 후, `~/.aws/config`에 등록한다.
예를 들어서, `cdk_user`라는 IAM User를 생성 한 후, 아래와 같이 `~/.aws/config`에 추가로 등록한다.

    ```shell script
    $ cat ~/.aws/config
    [profile cdk_user]
    aws_access_key_id=AKIAIOSFODNN7EXAMPLE
    aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
    region=us-east-1
    ```

1. 아래와 같이 소스 코드를 git clone 한 후에, python virtualenv 환경을 구성한다.

    ```shell script
    $ git clone https://github.com/ksmin23/aws-rss-feed-trans-bot-on-ecs.git
    $ cd aws-rss-feed-trans-bot-on-ecs
    $ cd cdk
    $ python3 -m venv .env
    $ source .env/bin/activate
    (.env) $ pip install -r requirements-cdk.txt
    ```

2. `cdk.context.json` 파일을 열어서, `vpc_name` 에 사용할 VPC 이름을 적는다.<br/>`s3_bucket_name_suffix`에 번역한 결과를 저장할 s3 bucket의 suffix를 적고,<br/>`email_from_address`과 `email_to_addresses`에 e-mail 발신자와 수신자들 목록을 각각 넣는다.<br/> RSS Feed를 읽는 주기를 변경하고자 하는 경우, `event_schedule`을 crontab 문법 처럼 등록 한다.<br/>
`event_schedule` 기본 값은 매 시간 마다 RSS Feed를 읽어서 번역한다.<br/>
`container_repository_name`, `container_image_tag`는 앞서 생성한 Amazon ECR Repository 이름과 Amazon ERC Repository에 push한 Docker 이미지 태그를 각각 등록한다.

    ```json
    {
        "vpc_name": "Your-VPC-Name",
        "s3_bucket_name_suffix": "Your-S3-Bucket-Name-Suffix",
        "email_from_address": "Your-Sender-Email-Addr",
        "email_to_addresses": "Your-Receiver-Email-Addr-List",
        "dry_run": "false",
        "trans_dest_lang": "ko",
        "event_schedule": "0 * * * *",
        "container_repository_name": "Your-ECR-Repository-Name",
        "container_image_tag": "Your-Container-Image-Tag"
    }
    ```

   `email_from_address`은 [Amazon SES에서 이메일 주소 확인](https://docs.aws.amazon.com/ses/latest/DeveloperGuide/verify-email-addresses.html)를 참고해서 반드시 사용 가능한 email 주소인지 확인한다. (배포 전에 한번만 확인 하면 된다.)
    예를 들어, `sender@amazon.com`라는 email 주소를 확인하려면 다음과 같이 한다.
      ```
      aws ses verify-email-identity --email-address sender@amazon.com
      ```

3. `cdk deploy` 명령어를 이용해서 배포한다.
    ```shell script
    (.env) $ cdk --profile=cdk_user deploy
    ```

4. 배포한 애플리케이션을 삭제하려면, `cdk destroy` 명령어를 아래와 같이 실행 한다.
    ```shell script
    (.env) $ cdk --profile=cdk_user destroy
    ```

##### Useful commands

 * `cdk ls`          list all stacks in the app
 * `cdk synth`       emits the synthesized CloudFormation template
 * `cdk deploy`      deploy this stack to your default AWS account/region
 * `cdk diff`        compare deployed stack with current state
 * `cdk docs`        open CDK documentation

## References

 * [Amazon ECR - Private registry authentication](https://docs.aws.amazon.com/AmazonECR/latest/userguide/registry_auth.html)
 * [Amazon ECR - Pushing an image](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-push.html)
 * [Amazon ECR - Pulling an image](https://docs.aws.amazon.com/AmazonECR/latest/userguide/docker-pull-ecr-image.html)
 * [aws cli - ecr](https://awscli.amazonaws.com/v2/documentation/api/latest/reference/ecr/index.html#cli-aws-ecr)
